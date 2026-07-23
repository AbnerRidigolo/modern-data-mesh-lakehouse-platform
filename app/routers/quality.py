import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from domains.common.paths import get_data_quality_dir

from ..security import get_current_user

logger = logging.getLogger("API_Quality")
router = APIRouter(prefix="/api/v1/data-quality", tags=["data-quality"])


@router.get("/report")
def get_data_quality_report(current_user: str = Depends(get_current_user)):
    report_file = os.path.join(get_data_quality_dir(), "dq_report.json")
    if not os.path.exists(report_file):
        raise HTTPException(status_code=404, detail="Relatório de qualidade de dados não encontrado. Execute a pipeline primeiro.")

    try:
        with open(report_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erro ao ler relatório de qualidade: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/history")
def get_data_quality_history(limit: int = 30, current_user: str = Depends(get_current_user)):
    history_file = os.path.join(get_data_quality_dir(), "dq_history.jsonl")
    if not os.path.exists(history_file):
        return []

    try:
        history = []
        with open(history_file, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    history.append(json.loads(line))
        return history[-limit:]
    except Exception as e:
        logger.error(f"Erro ao ler histórico de qualidade: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
