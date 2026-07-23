"""Analytics router: serve os marts analíticos ricos (camada semântica) que
alimentam o dashboard executivo e a página de Marketing do BI.

Todos os endpoints leem marts pré-computados pelo dbt (nada de agregação pesada
em request-time), passam por cache Redis com TTL curto e aceitam filtros de
período/categoria aplicados via parâmetros ligados (nunca interpolando entrada
do usuário direto no SQL).
"""
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import cache, run_query
from ..security import get_current_user

logger = logging.getLogger("API_Analytics")
router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def _stringify_dates(rows: list, cols: tuple) -> list:
    for row in rows:
        for col in cols:
            if row.get(col) is not None:
                row[col] = str(row[col])[:10]
    return rows


def _served(cache_key: str, sql: str, params: list, date_cols: tuple = ()):
    """Executa uma consulta parametrizada com cache e normalização de datas."""
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return {"source": "cache", "data": cached_val}

    try:
        start_time = time.time()
        data = run_query(sql, params)
        data = _stringify_dates(data, date_cols)
        query_time = time.time() - start_time
        cache.set(cache_key, data, ttl_seconds=60)
        return {"source": "database", "query_time_seconds": round(query_time, 4), "data": data}
    except Exception as e:
        logger.error(f"Erro em consulta de analytics ({cache_key}): {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/daily-revenue")
def get_daily_revenue(
    days: int = Query(90, ge=1, le=730, description="Janela de dias mais recentes"),
    current_user: str = Depends(get_current_user),
):
    """Série temporal diária de receita com média móvel 7d e delta dia-a-dia."""
    sql = (
        "SELECT revenue_date, net_revenue, orders, active_customers, "
        "revenue_7d_avg, revenue_dod_delta FROM dm_daily_revenue "
        "ORDER BY revenue_date DESC LIMIT ?"
    )
    result = _served(f"an_daily_revenue_{days}", sql, [days], date_cols=("revenue_date",))
    # devolvemos em ordem cronológica ascendente para o gráfico
    result["data"] = list(reversed(result["data"]))
    return result


@router.get("/category-performance")
def get_category_performance(current_user: str = Depends(get_current_user)):
    """Receita, pedidos, ticket médio e share por categoria de produto."""
    sql = (
        "SELECT category, net_revenue, orders, unique_customers, "
        "average_ticket, revenue_share_pct FROM dm_category_performance "
        "ORDER BY net_revenue DESC"
    )
    return _served("an_category_perf", sql, [])


@router.get("/cohorts")
def get_cohorts(current_user: str = Depends(get_current_user)):
    """Matriz de retenção por coorte de aquisição (para heatmap)."""
    sql = (
        "SELECT cohort_month, month_offset, cohort_customers, "
        "active_customers, retention_pct FROM dm_customer_cohorts "
        "ORDER BY cohort_month, month_offset"
    )
    return _served("an_cohorts", sql, [], date_cols=("cohort_month",))


@router.get("/marketing")
def get_marketing_performance(
    category: str | None = Query(None, description="Filtro por categoria de produto"),
    current_user: str = Depends(get_current_user),
):
    """Performance de marketing (spend, CTR, CPC, ROAS, CAC) por mês x categoria."""
    where = ""
    params: list = []
    if category:
        where = "WHERE category = ?"
        params.append(category)

    sql = (
        "SELECT activity_month, category, spend, impressions, clicks, orders, "
        "buyers, attributed_revenue, ctr_pct, cpc, cpm, roas, cac, "
        f"click_to_order_pct FROM dm_marketing_performance {where} "
        "ORDER BY activity_month DESC, spend DESC"
    )
    return _served(
        f"an_marketing_{category or 'all'}", sql, params, date_cols=("activity_month",)
    )
