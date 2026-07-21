import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from domains.common.paths import get_quarantine_dir
from domains.crm.contract import CustomerContract
from domains.ecommerce.contract import SaleContract

from ..security import get_current_user

logger = logging.getLogger("API_Catalog")
router = APIRouter(prefix="/api/v1", tags=["catalog"])


def _contract_fields(model) -> list:
    schema = model.model_json_schema()
    required = set(schema.get("required", []))
    fields = []
    for field_name, prop in schema.get("properties", {}).items():
        fields.append(
            {
                "name": field_name,
                "type": prop.get("type") or prop.get("format") or "any",
                "required": field_name in required,
                "description": prop.get("description", ""),
            }
        )
    return fields


DOMAINS = {
    "crm": {
        "name": "CRM (Cadastro de Clientes)",
        "owner": "Equipe de Relacionamento (CRM Team)",
        "interface": "Delta Lake Table (storage/lakehouse/crm/customers)",
        "write_stack": "Polars DataFrames (Rust-based)",
        "partitioning": None,
        "contract": lambda: _contract_fields(CustomerContract),
    },
    "ecommerce": {
        "name": "E-Commerce (Vendas)",
        "owner": "Equipe Comercial (E-Commerce Team)",
        "interface": "Delta Lake Table (storage/lakehouse/ecommerce/sales)",
        "write_stack": "Apache Spark (PySpark DataFrame API)",
        "partitioning": "status",
        "contract": lambda: _contract_fields(SaleContract),
    },
}


@router.get("/catalog/domains")
def get_catalog_domains(current_user: str = Depends(get_current_user)):
    return {
        key: {
            "name": meta["name"],
            "owner": meta["owner"],
            "interface": meta["interface"],
            "write_stack": meta["write_stack"],
            "partitioning": meta["partitioning"],
            "contract_fields": meta["contract"](),
        }
        for key, meta in DOMAINS.items()
    }


@router.get("/quarantine/{domain}")
def list_quarantine(domain: str, current_user: str = Depends(get_current_user)):
    if domain not in DOMAINS:
        raise HTTPException(status_code=404, detail=f"Domínio '{domain}' desconhecido.")

    q_dir = get_quarantine_dir(domain)
    if not os.path.exists(q_dir):
        return {"files": []}

    return {"files": sorted(os.listdir(q_dir))}


@router.get("/quarantine/{domain}/{file_name}")
def get_quarantine_file(domain: str, file_name: str, current_user: str = Depends(get_current_user)):
    if domain not in DOMAINS:
        raise HTTPException(status_code=404, detail=f"Domínio '{domain}' desconhecido.")

    q_dir = get_quarantine_dir(domain)
    safe_name = os.path.basename(file_name)
    file_path = os.path.join(q_dir, safe_name)

    if not os.path.exists(file_path) or not os.path.abspath(file_path).startswith(os.path.abspath(q_dir)):
        raise HTTPException(status_code=404, detail="Arquivo de quarentena não encontrado.")

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    try:
        return {"file_name": safe_name, "content": json.loads(content)}
    except json.JSONDecodeError:
        return {"file_name": safe_name, "content": content, "raw": True}
