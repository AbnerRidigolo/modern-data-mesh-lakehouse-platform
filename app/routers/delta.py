import logging
import os

import pandas as pd
from deltalake import DeltaTable
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from domains.common.paths import DELTA_TABLES, get_delta_read_options, get_delta_table_path, s3_enabled

from ..security import get_current_user

logger = logging.getLogger("API_Delta")
router = APIRouter(prefix="/api/v1/delta", tags=["delta"])

TABLE_LABELS = {
    "crm_customers": "CRM Customers",
    "ecommerce_sales": "E-Commerce Sales",
}


def _resolve_table(table_key: str) -> DeltaTable:
    if table_key not in DELTA_TABLES:
        raise HTTPException(status_code=404, detail=f"Data product '{table_key}' desconhecido.")

    path = get_delta_table_path(table_key)
    options = get_delta_read_options()

    if not s3_enabled() and not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"A tabela Delta '{table_key}' ainda não foi criada. Execute a pipeline no Airflow.")

    try:
        return DeltaTable(path, storage_options=options)
    except Exception:
        raise HTTPException(status_code=404, detail=f"A tabela Delta '{table_key}' ainda não foi criada. Execute a pipeline no Airflow.") from None


def _jsonable_records(df: pd.DataFrame) -> list:
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].astype(str)
    return df.where(pd.notnull(df), None).to_dict(orient="records")


@router.get("/tables")
def list_tables(current_user: str = Depends(get_current_user)):
    tables = []
    for key in DELTA_TABLES:
        path = get_delta_table_path(key)
        exists = True
        if not s3_enabled():
            exists = os.path.exists(path)
        else:
            try:
                DeltaTable(path, storage_options=get_delta_read_options())
            except Exception:
                exists = False
        tables.append({"key": key, "label": TABLE_LABELS.get(key, key), "exists": exists})
    return tables


@router.get("/{table_key}/history")
def get_table_history(table_key: str, current_user: str = Depends(get_current_user)):
    dt = _resolve_table(table_key)
    history = dt.history()

    result = []
    for h in history:
        entry = {
            "version": h.get("version"),
            "operation": h.get("operation"),
            "userName": h.get("userName"),
            "operationParameters": h.get("operationParameters"),
        }
        ts = h.get("timestamp")
        entry["timestamp"] = pd.to_datetime(ts, unit="ms").isoformat() if ts is not None else None
        result.append(entry)

    return sorted(result, key=lambda r: r["version"])


@router.get("/{table_key}/data")
def get_table_data(table_key: str, version: int = None, limit: int = 200, current_user: str = Depends(get_current_user)):
    path = get_delta_table_path(table_key)
    options = get_delta_read_options()

    if table_key not in DELTA_TABLES:
        raise HTTPException(status_code=404, detail=f"Data product '{table_key}' desconhecido.")

    try:
        dt = DeltaTable(path, version=version, storage_options=options) if version is not None else DeltaTable(path, storage_options=options)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Erro ao ler a versão solicitada: {e}") from e

    df = dt.to_pandas()
    total_rows = len(df)
    df = df.head(limit)

    return {"version": version if version is not None else dt.version(), "total_rows": total_rows, "returned_rows": len(df), "records": _jsonable_records(df)}


class RestoreRequest(BaseModel):
    version: int


@router.post("/{table_key}/restore")
def restore_table(table_key: str, payload: RestoreRequest, current_user: str = Depends(get_current_user)):
    dt = _resolve_table(table_key)
    latest_version = dt.version()

    if payload.version == latest_version:
        return {"message": "A tabela já está na versão selecionada.", "version": latest_version}

    try:
        dt.restore(payload.version)
    except Exception as e:
        logger.error(f"Erro ao executar restore em '{table_key}': {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao executar restore: {e}") from e

    return {"message": f"Tabela '{table_key}' restaurada com sucesso para a Versão {payload.version}!", "version": payload.version}
