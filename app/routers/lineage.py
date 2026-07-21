import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from domains.common.paths import get_dbt_manifest_path

from ..security import get_current_user

logger = logging.getLogger("API_Lineage")
router = APIRouter(prefix="/api/v1/lineage", tags=["lineage"])


def _layer_for(name: str) -> str:
    if name.startswith("stg_"):
        return "staging"
    if name.startswith("dim_"):
        return "dimension"
    if name.startswith("fct_"):
        return "fact"
    if name.startswith("ml_") or name.startswith("dm_"):
        return "mart"
    return "other"


@router.get("")
def get_dbt_lineage(current_user: str = Depends(get_current_user)):
    manifest_path = get_dbt_manifest_path()
    if not os.path.exists(manifest_path):
        raise HTTPException(
            status_code=404,
            detail="Linhagem dbt indisponível. Execute a pipeline no Airflow para gerar o manifest.json (dbt docs generate).",
        )

    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        logger.error(f"Erro ao carregar linhagem dbt: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e

    nodes = manifest.get("nodes", {})
    dag_nodes = {}

    for node_info in nodes.values():
        if node_info.get("resource_type") == "model" and node_info.get("package_name") == "analytics_dw":
            name = node_info.get("name")
            depends_on = node_info.get("depends_on", {}).get("nodes", [])
            parents = []
            for p_id in depends_on:
                if p_id.startswith("model.analytics_dw."):
                    parents.append(p_id.split(".")[-1])
                elif p_id.startswith("source.analytics_dw."):
                    parts = p_id.split(".")
                    parents.append(f"{parts[-2]}.{parts[-1]}")
            dag_nodes[name] = {"parents": parents, "layer": _layer_for(name)}

    return {"nodes": dag_nodes}
