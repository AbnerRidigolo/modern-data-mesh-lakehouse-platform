import logging

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_feature_store
from ..security import get_current_user

logger = logging.getLogger("API_Features")
router = APIRouter(prefix="/api/v1/features", tags=["feature-store"])


@router.get("/registry")
def get_registry(current_user: str = Depends(get_current_user)):
    """Catálogo governado: entidades, feature views, features, owners e TTL."""
    try:
        return get_feature_store().catalog()
    except Exception as e:
        logger.error(f"Erro ao carregar registry do feature store: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/freshness")
def get_freshness(current_user: str = Depends(get_current_user)):
    """Frescor por feature view: idade do dado mais recente vs TTL."""
    try:
        return get_feature_store().freshness()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Erro ao calcular frescor: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/online/{view_name}/{entity_id}")
def get_online(view_name: str, entity_id: str, current_user: str = Depends(get_current_user)):
    """Serving online: vetor de features de uma entidade em baixa latência."""
    store = get_feature_store()
    try:
        view = store.registry["feature_views"].get(view_name)
        if view is None:
            raise HTTPException(status_code=404, detail=f"Feature view '{view_name}' não existe.")
        # Chave de customer é inteira; product é string
        join_key = store.registry["entities"][view["entity"]]["join_key"]
        key_value: object = entity_id
        if join_key == "customer_id":
            try:
                key_value = int(entity_id)
            except ValueError as e:
                raise HTTPException(status_code=400, detail="customer_id deve ser um inteiro.") from e
        result = store.get_online_features(view_name, key_value)
        if result.get("source") == "not_found":
            raise HTTPException(status_code=404, detail=f"Entidade '{entity_id}' não encontrada em '{view_name}'.")
        return result
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Erro no serving online: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/materialize")
def materialize(current_user: str = Depends(get_current_user)):
    """Materializa o snapshot mais recente por entidade para o online store (Redis)."""
    try:
        return {"status": "ok", "views": get_feature_store().materialize()}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Erro ao materializar features: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
