import datetime
import json
import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException

from domains.common.paths import get_logs_dir, get_model_dir

from ..deps import cache, get_embedding_model, qdrant_client
from ..security import get_current_user

logger = logging.getLogger("API_Search")
router = APIRouter(prefix="/api/v1", tags=["search"])

COLLECTION_NAME = "products"


def _log_search_event(query: str, latency_seconds: float, source: str, top_match: str = None, top_score: float = 0.0):
    logs_dir = get_logs_dir()
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, "search_logs.jsonl")

    log_entry = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "query": query,
        "latency_seconds": round(latency_seconds, 4),
        "source": source,
        "top_match": top_match or "Nenhum",
        "top_score": round(top_score, 4),
    }

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        logger.error(f"Erro ao salvar log de busca: {e}")


def _lookup_pricing_details(product_name: str):
    metadata_file = os.path.join(get_model_dir(), "pricing_metadata.json")
    if not os.path.exists(metadata_file):
        return None
    try:
        with open(metadata_file, encoding="utf-8") as f:
            meta = json.load(f)
        optimal_prices = meta.get("optimal_prices", {})
        hit_name = product_name.lower()
        for name, details in optimal_prices.items():
            if name.lower() in hit_name or hit_name in name.lower():
                return {
                    "base_price": details.get("base_price"),
                    "optimal_price": details.get("optimal_price"),
                    "revenue_lift_pct": details.get("revenue_lift_pct"),
                }
    except Exception as ex:
        logger.warning(f"Erro ao buscar detalhes de precificação para {product_name}: {ex}")
    return None


@router.get("/products/search")
def search_products(query: str, current_user: str = Depends(get_current_user)):
    start_time = time.time()
    if not query:
        raise HTTPException(status_code=400, detail="O parâmetro 'query' não pode ser vazio.")

    cache_key = f"product_search_{query.lower().strip().replace(' ', '_')}"

    cached_val = cache.get(cache_key)
    if cached_val is not None:
        latency = time.time() - start_time
        top_match = cached_val[0].get("name") if cached_val else "Nenhum"
        top_score = cached_val[0].get("score") if cached_val else 0.0
        _log_search_event(query, latency, "cache", top_match, top_score)
        return {"source": "cache", "query_time_seconds": round(latency, 4), "data": cached_val}

    try:
        model = get_embedding_model()
        query_vector = list(model.embed([query]))[0].tolist()

        try:
            collections = qdrant_client.get_collections().collections
            exists = any(c.name == COLLECTION_NAME for c in collections)
        except Exception as q_err:
            logger.error(f"Erro ao obter coleções do Qdrant: {q_err}")
            exists = False

        if not exists:
            latency = time.time() - start_time
            _log_search_event(query, latency, "database_qdrant", "Nenhum", 0.0)
            return {"source": "database_qdrant", "query_time_seconds": round(latency, 4), "data": []}

        search_result = qdrant_client.search(collection_name=COLLECTION_NAME, query_vector=query_vector, limit=5)

        results = []
        for hit in search_result:
            results.append(
                {
                    "id": hit.id,
                    "score": round(hit.score, 4),
                    "name": hit.payload.get("name"),
                    "description": hit.payload.get("description"),
                    "category": hit.payload.get("category"),
                    "pricing_details": _lookup_pricing_details(hit.payload.get("name", "")),
                }
            )

        query_time = time.time() - start_time
        top_match = results[0].get("name") if results else "Nenhum"
        top_score = results[0].get("score") if results else 0.0
        _log_search_event(query, query_time, "database_qdrant", top_match, top_score)

        cache.set(cache_key, results, ttl_seconds=120)

        return {"source": "database_qdrant", "query_time_seconds": round(query_time, 4), "data": results}
    except Exception as e:
        logger.error(f"Erro na busca vetorial: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/search/logs")
def get_search_logs(limit: int = 50, current_user: str = Depends(get_current_user)):
    log_file = os.path.join(get_logs_dir(), "search_logs.jsonl")
    if not os.path.exists(log_file):
        return []

    try:
        logs = []
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))
        return logs[::-1][:limit]
    except Exception as e:
        logger.error(f"Erro ao ler logs de busca: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
