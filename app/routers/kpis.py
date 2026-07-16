import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from ..deps import cache, run_query
from ..security import get_current_user

logger = logging.getLogger("API_KPIs")
router = APIRouter(prefix="/api/v1", tags=["kpis"])


@router.get("/kpis")
def get_kpis(current_user: str = Depends(get_current_user)):
    cache_key = "kpis_monthly"

    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return {"source": "cache", "data": cached_val}

    try:
        start_time = time.time()
        data = run_query("SELECT * FROM dm_monthly_kpis")
        for row in data:
            if "sales_month" in row and row["sales_month"]:
                row["sales_month"] = str(row["sales_month"])[:10]

        query_time = time.time() - start_time
        cache.set(cache_key, data, ttl_seconds=60)

        return {"source": "database", "query_time_seconds": round(query_time, 4), "data": data}
    except Exception as e:
        logger.error(f"Erro ao consultar KPIs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customers")
def get_customers(current_user: str = Depends(get_current_user)):
    cache_key = "customers_list"

    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return {"source": "cache", "data": cached_val}

    try:
        start_time = time.time()
        data = run_query(
            "SELECT customer_id, customer_name, email, created_at, status FROM dim_customers LIMIT 100"
        )
        for row in data:
            if "created_at" in row and row["created_at"]:
                row["created_at"] = str(row["created_at"])

        query_time = time.time() - start_time
        cache.set(cache_key, data, ttl_seconds=60)

        return {"source": "database", "query_time_seconds": round(query_time, 4), "data": data}
    except Exception as e:
        logger.error(f"Erro ao consultar clientes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
def clear_cache(current_user: str = Depends(get_current_user)):
    cache.clear()
    return {"message": "Todos os caches limpos."}
