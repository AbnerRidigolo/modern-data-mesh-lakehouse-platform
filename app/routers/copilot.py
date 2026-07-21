import logging

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config
from ..security import get_current_user

logger = logging.getLogger("API_Copilot")
router = APIRouter(prefix="/api/v1/copilot", tags=["ai-copilot"])


class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


@router.get("/status")
def copilot_status(current_user: str = Depends(get_current_user)):
    return {
        "enabled": config.COPILOT_ENABLED,
        "model": config.COPILOT_MODEL if config.COPILOT_ENABLED else None,
    }


@router.post("/chat")
def copilot_chat(payload: ChatRequest, current_user: str = Depends(get_current_user)):
    if not config.COPILOT_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="AI Copilot desabilitado: defina ANTHROPIC_API_KEY no ambiente da API para ativá-lo.",
        )

    from ..services import copilot

    try:
        return copilot.chat(payload.message, [t.model_dump() for t in payload.history])
    except anthropic.AuthenticationError as e:
        raise HTTPException(status_code=503, detail="Credencial da Anthropic inválida.") from e
    except anthropic.RateLimitError as e:
        raise HTTPException(status_code=429, detail="Limite de requisições do provedor de IA atingido. Tente novamente em instantes.") from e
    except anthropic.APIConnectionError as e:
        raise HTTPException(status_code=502, detail="Falha de conexão com o provedor de IA.") from e
    except anthropic.APIStatusError as e:
        logger.error(f"Erro da API Anthropic: {e.status_code} {e.message}")
        raise HTTPException(status_code=502, detail="Erro no provedor de IA.") from e
