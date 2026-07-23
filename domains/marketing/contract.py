from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class MarketingEventContract(BaseModel):
    """Contrato de dados do domínio de Marketing: gasto e engajamento diário de
    uma campanha, por canal e categoria-alvo. Alimenta a atribuição de ROI/CAC."""

    event_id: int = Field(..., description="ID único do evento de campanha")
    campaign: str = Field(..., min_length=2, description="Nome da campanha")
    channel: str = Field(..., description="Canal de mídia")
    category: str = Field(..., description="Categoria de produto alvo da campanha")
    spend: float = Field(..., description="Investimento em mídia no dia (deve ser > 0)")
    impressions: int = Field(..., ge=0, description="Impressões servidas")
    clicks: int = Field(..., ge=0, description="Cliques recebidos")
    event_date: datetime = Field(..., description="Data do evento de campanha")

    @field_validator("spend")
    @classmethod
    def validate_spend(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"Investimento deve ser estritamente positivo. Recebido: {v}")
        return v

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        allowed = {"Google Ads", "Meta Ads", "Email", "Influencer"}
        if v not in allowed:
            raise ValueError(f"Canal '{v}' inválido. Valores permitidos: {allowed}")
        return v

    @model_validator(mode="after")
    def clicks_not_exceed_impressions(self) -> "MarketingEventContract":
        if self.clicks > self.impressions:
            raise ValueError(
                f"Cliques ({self.clicks}) não podem exceder impressões ({self.impressions})."
            )
        return self
