import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query

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
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/customers")
def get_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: str = Depends(get_current_user),
):
    cache_key = f"customers_list_p{page}_s{page_size}"

    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return {"source": "cache", **cached_val}

    try:
        start_time = time.time()
        total = run_query("SELECT COUNT(*) AS n FROM dim_customers")[0]["n"]
        offset = (page - 1) * page_size
        data = run_query(
            "SELECT customer_id, customer_name, email, created_at, status FROM dim_customers "
            f"ORDER BY customer_id LIMIT {page_size} OFFSET {offset}"
        )
        for row in data:
            if "created_at" in row and row["created_at"]:
                row["created_at"] = str(row["created_at"])

        query_time = time.time() - start_time
        payload = {
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_rows": total,
                "total_pages": max(1, -(-total // page_size)),
            },
            "data": data,
        }
        cache.set(cache_key, payload, ttl_seconds=60)

        return {"source": "database", "query_time_seconds": round(query_time, 4), **payload}
    except Exception as e:
        logger.error(f"Erro ao consultar clientes: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/customers/ltv")
def get_customer_ltv(
    segment: str = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: str = Depends(get_current_user),
):
    """Mart de valor do cliente (LTV + segmentação RFM) calculado pelo dbt."""
    cache_key = f"customer_ltv_{segment or 'all'}_{limit}"

    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return {"source": "cache", "data": cached_val}

    try:
        start_time = time.time()
        where = ""
        if segment:
            safe_segment = segment.replace("'", "''")
            where = f"WHERE rfm_segment = '{safe_segment}'"
        data = run_query(
            f"SELECT * FROM dm_customer_ltv {where} ORDER BY lifetime_value DESC LIMIT {limit}"
        )
        for row in data:
            for col in ("first_purchase_at", "last_purchase_at"):
                if row.get(col):
                    row[col] = str(row[col])

        query_time = time.time() - start_time
        cache.set(cache_key, data, ttl_seconds=60)

        return {"source": "database", "query_time_seconds": round(query_time, 4), "data": data}
    except Exception as e:
        logger.error(f"Erro ao consultar LTV de clientes: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/cache/clear")
def clear_cache(current_user: str = Depends(get_current_user)):
    cache.clear()
    return {"message": "Todos os caches limpos."}
