import json
import logging
import os

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..deps import cache
from ..security import get_current_user
from domains.common.paths import get_model_dir

logger = logging.getLogger("API_ML")
router = APIRouter(prefix="/api/v1", tags=["ml"])

_model_cache = {"model": None, "metadata": None, "mtime": None}


def _model_paths():
    model_dir = get_model_dir()
    return (
        os.path.join(model_dir, "pricing_model.joblib"),
        os.path.join(model_dir, "pricing_metadata.json"),
    )


def _load_model_and_metadata():
    model_path, metadata_path = _model_paths()
    if not os.path.exists(model_path) or not os.path.exists(metadata_path):
        raise HTTPException(
            status_code=404,
            detail="O modelo de ML e os metadados de otimização ainda não foram gerados. Execute a DAG do Airflow.",
        )

    mtime = os.path.getmtime(model_path)
    if _model_cache["model"] is None or _model_cache["mtime"] != mtime:
        import joblib

        _model_cache["model"] = joblib.load(model_path)
        with open(metadata_path, "r", encoding="utf-8") as mf:
            _model_cache["metadata"] = json.load(mf)
        _model_cache["mtime"] = mtime

    return _model_cache["model"], _model_cache["metadata"]


@router.get("/predict/optimal-price")
def get_optimal_price(product_name: str = None, current_user: str = Depends(get_current_user)):
    cache_key = f"optimal_price_{product_name.lower().replace(' ', '_')}" if product_name else "optimal_price_all"

    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return {"source": "cache", "data": cached_val}

    _, metadata_path = _model_paths()
    if not os.path.exists(metadata_path):
        raise HTTPException(status_code=404, detail="Metadados de precificação não encontrados. O modelo de ML precisa ser treinado primeiro.")

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        optimal_prices = metadata.get("optimal_prices", {})

        if product_name:
            matched_data = None
            for name, details in optimal_prices.items():
                if name.lower() == product_name.lower():
                    matched_data = {"product_name": name, **details}
                    break
            if not matched_data:
                raise HTTPException(status_code=404, detail=f"Produto '{product_name}' não encontrado nos resultados de otimização.")

            cache.set(cache_key, matched_data, ttl_seconds=60)
            return {"source": "database_json", "data": matched_data}

        cache.set(cache_key, optimal_prices, ttl_seconds=60)
        return {"source": "database_json", "data": optimal_prices}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter preço ótimo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ml/pricing-metadata")
def get_pricing_metadata(current_user: str = Depends(get_current_user)):
    _, metadata = _load_model_and_metadata()
    return metadata


@router.get("/ml/drift-status")
def get_drift_status(current_user: str = Depends(get_current_user)):
    drift_path = os.path.join(get_model_dir(), "drift_status.json")
    if not os.path.exists(drift_path):
        raise HTTPException(status_code=404, detail="Nenhum dado de monitoramento de drift gerado ainda.")
    with open(drift_path, "r", encoding="utf-8") as rf:
        return json.load(rf)


@router.get("/ml/drift-report", response_class=HTMLResponse)
def get_drift_report_html(current_user: str = Depends(get_current_user)):
    report_path = os.path.join(get_model_dir(), "drift_report.html")
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Relatório detalhado do Evidently AI ainda não foi gerado.")
    with open(report_path, "r", encoding="utf-8") as f:
        return f.read()


class SimulationRequest(BaseModel):
    product_name: str
    price: float = Field(..., gt=0)
    is_weekend: bool = False


@router.post("/ml/simulate")
def simulate_pricing(payload: SimulationRequest, current_user: str = Depends(get_current_user)):
    model, metadata = _load_model_and_metadata()
    optimal_prices = metadata.get("optimal_prices", {})

    matched_name = next((name for name in optimal_prices if name.lower() == payload.product_name.lower()), None)
    if not matched_name:
        raise HTTPException(status_code=404, detail=f"Produto '{payload.product_name}' não encontrado.")

    prod_details = optimal_prices[matched_name]
    feature_cols = metadata["feature_columns"]
    product_cols = metadata["product_one_hot_columns"]

    row = {
        "price": payload.price,
        "competitor_price": prod_details["competitor_price"],
        "day_of_week": 6 if payload.is_weekend else 3,
        "is_weekend": 1 if payload.is_weekend else 0,
    }
    for col in product_cols:
        row[col] = 1 if col == f"prod_{matched_name}" else 0

    sim_df = pd.DataFrame([row])[feature_cols]
    demand = float(model.predict(sim_df)[0])
    revenue = payload.price * demand

    current_revenue = prod_details["current_daily_revenue"]
    lift_pct = ((revenue - current_revenue) / current_revenue) * 100 if current_revenue > 0 else 0.0

    return {
        "product_name": matched_name,
        "simulated_price": payload.price,
        "projected_demand": round(demand, 2),
        "projected_revenue": round(revenue, 2),
        "lift_vs_baseline_pct": round(lift_pct, 2),
    }
