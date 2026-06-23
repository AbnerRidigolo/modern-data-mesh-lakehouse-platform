import pytest
from pydantic import ValidationError
from datetime import datetime

# Setup PYTHONPATH imports
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from domains.crm.contract import CustomerContract
from domains.ecommerce.contract import SaleContract

def test_valid_customer_contract():
    valid_data = {
        "id": 123,
        "name": "João Silva",
        "email": "joao@exemplo.com",
        "created_at": "2026-06-19T12:00:00",
        "status": "active"
    }
    contract = CustomerContract(**valid_data)
    assert contract.id == 123
    assert contract.name == "João Silva"
    assert contract.email == "joao@exemplo.com"
    assert contract.status == "active"

def test_invalid_customer_email():
    invalid_data = {
        "id": 123,
        "name": "João Silva",
        "email": "joao_invalid_email",
        "created_at": "2026-06-19T12:00:00",
        "status": "active"
    }
    with pytest.raises(ValidationError) as exc_info:
        CustomerContract(**invalid_data)
    assert "email" in str(exc_info.value)

def test_invalid_customer_status():
    invalid_data = {
        "id": 123,
        "name": "João Silva",
        "email": "joao@exemplo.com",
        "created_at": "2026-06-19T12:00:00",
        "status": "suspended"
    }
    with pytest.raises(ValidationError) as exc_info:
        CustomerContract(**invalid_data)
    assert "suspended" in str(exc_info.value)

def test_valid_sale_contract():
    valid_data = {
        "sale_id": 999,
        "customer_id": 123,
        "product": "Teclado Mecânico Keychron",
        "amount": 600.0,
        "competitor_price": 590.0,
        "status": "COMPLETED",
        "sale_date": "2026-06-19T12:30:00"
    }
    contract = SaleContract(**valid_data)
    assert contract.sale_id == 999
    assert contract.amount == 600.0
    assert contract.status == "COMPLETED"

def test_invalid_sale_amount():
    invalid_data = {
        "sale_id": 999,
        "customer_id": 123,
        "product": "Teclado Mecânico Keychron",
        "amount": -50.0,
        "competitor_price": 590.0,
        "status": "COMPLETED",
        "sale_date": "2026-06-19T12:30:00"
    }
    with pytest.raises(ValidationError) as exc_info:
        SaleContract(**invalid_data)
    assert "positivo" in str(exc_info.value)

def test_invalid_sale_status():
    invalid_data = {
        "sale_id": 999,
        "customer_id": 123,
        "product": "Teclado Mecânico Keychron",
        "amount": 600.0,
        "competitor_price": 590.0,
        "status": "SHIPPED",
        "sale_date": "2026-06-19T12:30:00"
    }
    with pytest.raises(ValidationError) as exc_info:
        SaleContract(**invalid_data)
    assert "SHIPPED" in str(exc_info.value)
