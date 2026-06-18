from pydantic import BaseModel, Field, field_validator
from datetime import datetime

class SaleContract(BaseModel):
    sale_id: int = Field(..., description="ID da transação de venda")
    customer_id: int = Field(..., description="ID do cliente (chave estrangeira)")
    product: str = Field(..., min_length=2, description="Nome do produto vendido")
    amount: float = Field(..., description="Valor total da venda (deve ser positivo)")
    status: str = Field(..., description="Status do processamento da venda")
    sale_date: datetime = Field(..., description="Data/hora em que a venda foi realizada")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"Valor da venda deve ser estritamente positivo. Recebido: {v}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"COMPLETED", "PENDING", "CANCELLED"}
        if v not in allowed:
            raise ValueError(f"Status '{v}' inválido. Valores permitidos: {allowed}")
        return v
