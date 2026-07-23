from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class CustomerContract(BaseModel):
    id: int = Field(..., description="ID único do cliente")
    name: str = Field(..., min_length=2, description="Nome completo do cliente")
    email: EmailStr = Field(..., description="Endereço de e-mail válido")
    created_at: datetime = Field(..., description="Timestamp de criação do registro")
    status: str = Field(..., description="Status do cadastro (active ou inactive)")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"active", "inactive"}
        if v not in allowed:
            raise ValueError(f"Status '{v}' é inválido. Valores permitidos: {allowed}")
        return v
