import os
import json
import logging
import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
try:
    from .cache import RedisCacheWrapper
except (ImportError, ValueError):
    from cache import RedisCacheWrapper
import time
from qdrant_client import QdrantClient
from fastembed import TextEmbedding

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("API_Gateway")

app = FastAPI(
    title="Data-as-a-Service (DaaS) API Gateway",
    description="Exposição segura e cacheada de produtos de dados e KPIs do central Data Warehouse",
    version="1.0.0"
)

# Enable CORS for Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dynamically locate DuckDB file
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
local_db = os.path.join(base_dir, "storage", "analytics.duckdb")
container_db = "/opt/airflow/storage/analytics.duckdb"

db_path = os.environ.get("DB_PATH")
if not db_path:
    db_path = container_db if os.path.exists(container_db) else local_db

logger.info(f"Conectando com o banco de dados analítico: {db_path}")

# Initialize Redis cache (connects to redis container or localhost)
redis_host = os.environ.get("REDIS_HOST", "localhost")
redis_port = int(os.environ.get("REDIS_PORT", 6389))
cache = RedisCacheWrapper(host=redis_host, port=redis_port)

def run_query(query: str) -> list:
    """Helper function to execute read-only queries on DuckDB."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Arquivo do DuckDB não encontrado em: {db_path}. Execute a pipeline primeiro.")
        
    conn = duckdb.connect(db_path, read_only=True)
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        # Fetch columns
        columns = [desc[0] for desc in cursor.description]
        # Fetch records
        rows = cursor.fetchall()
        # Convert to list of dicts
        results = [dict(zip(columns, row)) for row in rows]
        return results
    finally:
        conn.close()

@app.get("/")
def read_root():
    return {
        "status": "healthy",
        "api_version": "1.0.0",
        "database_connected": os.path.exists(db_path),
        "database_path": db_path,
        "cache_type": "Redis" if cache.enabled else "In-Memory Fallback"
    }

@app.get("/api/v1/kpis")
def get_kpis():
    cache_key = "kpis_monthly"
    
    # Try getting from cache
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return {
            "source": "cache",
            "data": cached_val
        }
        
    # Query Database on Cache Miss
    try:
        start_time = time.time()
        query = "SELECT * FROM dm_monthly_kpis"
        data = run_query(query)
        # Format date objects to string for JSON serialization
        for row in data:
            if "sales_month" in row and row["sales_month"]:
                row["sales_month"] = str(row["sales_month"])[:10] # YYYY-MM-DD
                
        query_time = time.time() - start_time
        logger.info(f"Query executada em {query_time:.4f}s. Salvando no cache.")
        
        # Save to cache with 60s TTL
        cache.set(cache_key, data, ttl_seconds=60)
        
        return {
            "source": "database",
            "query_time_seconds": round(query_time, 4),
            "data": data
        }
    except Exception as e:
        logger.error(f"Erro ao consultar KPIs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/customers")
def get_customers():
    cache_key = "customers_list"
    
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return {
            "source": "cache",
            "data": cached_val
        }
        
    try:
        start_time = time.time()
        query = "SELECT customer_id, customer_name, email, created_at, status FROM dim_customers LIMIT 100"
        data = run_query(query)
        for row in data:
            if "created_at" in row and row["created_at"]:
                row["created_at"] = str(row["created_at"])
                
        query_time = time.time() - start_time
        logger.info(f"Query executada em {query_time:.4f}s. Salvando no cache.")
        
        cache.set(cache_key, data, ttl_seconds=60)
        
        return {
            "source": "database",
            "query_time_seconds": round(query_time, 4),
            "data": data
        }
    except Exception as e:
        logger.error(f"Erro ao consultar clientes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/cache/clear")
def clear_cache():
    cache.clear()
    return {"message": "Todos os caches limpos."}

# Dynamically locate Model Registry directory
model_dir_local = os.path.join(base_dir, "storage", "model_registry")
model_dir_container = "/opt/airflow/storage/model_registry"
model_dir = model_dir_container if os.path.exists(model_dir_container) else model_dir_local

@app.get("/api/v1/predict/optimal-price")
def get_optimal_price(product_name: str = None):
    # If product_name is provided, use it to construct cache key
    cache_key = f"optimal_price_{product_name.lower().replace(' ', '_')}" if product_name else "optimal_price_all"
    
    # Try getting from cache
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return {
            "source": "cache",
            "data": cached_val
        }
        
    # Read metadata file
    metadata_file = os.path.join(model_dir, "pricing_metadata.json")
    if not os.path.exists(metadata_file):
        raise HTTPException(
            status_code=404, 
            detail="Metadados de precificação não encontrados. O modelo de ML precisa ser treinado primeiro."
        )
        
    try:
        with open(metadata_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            
        optimal_prices = metadata.get("optimal_prices", {})
        
        if product_name:
            # Case-insensitive lookup
            matched_data = None
            for name, details in optimal_prices.items():
                if name.lower() == product_name.lower():
                    matched_data = {
                        "product_name": name,
                        **details
                    }
                    break
            if not matched_data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Produto '{product_name}' não encontrado nos resultados de otimização."
                )
            
            # Cache the response
            cache.set(cache_key, matched_data, ttl_seconds=60)
            return {
                "source": "database_json",
                "data": matched_data
            }
        else:
            # Cache the response for all
            cache.set(cache_key, optimal_prices, ttl_seconds=60)
            return {
                "source": "database_json",
                "data": optimal_prices
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter preço ótimo: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Initialize Qdrant Client for API gateway
qdrant_host = os.environ.get("QDRANT_HOST", "localhost")
qdrant_port = int(os.environ.get("QDRANT_PORT", 6335))
qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)

# Lazy-loaded text embedding model
_embedding_model = None

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        logger.info("Carregando modelo de embeddings FastEmbed no FastAPI...")
        _embedding_model = TextEmbedding()
    return _embedding_model

@app.get("/api/v1/products/search")
def search_products(query: str):
    if not query:
        raise HTTPException(status_code=400, detail="O parâmetro 'query' não pode ser vazio.")
        
    cache_key = f"product_search_{query.lower().strip().replace(' ', '_')}"
    
    # Tenta obter do cache
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return {
            "source": "cache",
            "data": cached_val
        }
        
    try:
        start_time = time.time()
        
        # 1. Obter modelo de embedding e vetorizar query
        model = get_embedding_model()
        query_vector = list(model.embed([query]))[0].tolist()
        
        # 2. Consultar o Qdrant
        collection_name = "products"
        
        # Verificar se a coleção existe
        try:
            collections = qdrant_client.get_collections().collections
            exists = any(c.name == collection_name for c in collections)
        except Exception as q_err:
            logger.error(f"Erro ao obter coleções do Qdrant: {q_err}")
            exists = False
        
        if not exists:
            # Caso a coleção não exista, retorna uma lista vazia
            return {
                "source": "database_qdrant",
                "query_time_seconds": round(time.time() - start_time, 4),
                "data": []
            }
            
        search_result = qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=5
        )
        
        # 3. Formatar resultados
        results = []
        for hit in search_result:
            pricing_details = None
            metadata_file = os.path.join(model_dir, "pricing_metadata.json")
            if os.path.exists(metadata_file):
                try:
                    with open(metadata_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    optimal_prices = meta.get("optimal_prices", {})
                    
                    # Tentar fazer um lookup case-insensitive e parcial
                    hit_name = hit.payload.get("name", "").lower()
                    for name, details in optimal_prices.items():
                        if name.lower() in hit_name or hit_name in name.lower():
                            pricing_details = {
                                "base_price": details.get("base_price"),
                                "optimal_price": details.get("optimal_price"),
                                "revenue_lift_pct": details.get("revenue_lift_pct")
                            }
                            break
                except Exception as ex:
                    logger.warning(f"Erro ao buscar detalhes de precificação para {hit.payload.get('name')}: {ex}")
            
            results.append({
                "id": hit.id,
                "score": round(hit.score, 4),
                "name": hit.payload.get("name"),
                "description": hit.payload.get("description"),
                "category": hit.payload.get("category"),
                "pricing_details": pricing_details
            })
            
        query_time = time.time() - start_time
        logger.info(f"Busca vetorial executada em {query_time:.4f}s. Salvando no cache.")
        
        cache.set(cache_key, results, ttl_seconds=120)
        
        return {
            "source": "database_qdrant",
            "query_time_seconds": round(query_time, 4),
            "data": results
        }
    except Exception as e:
        logger.error(f"Erro na busca vetorial: {e}")
        raise HTTPException(status_code=500, detail=str(e))
