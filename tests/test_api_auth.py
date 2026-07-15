import pytest
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app

client = TestClient(app)

def test_token_auth_success():
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "admin", "password": "adminpassword"}
    )
    assert response.status_code == 200
    json_data = response.json()
    assert "access_token" in json_data
    assert json_data["token_type"] == "bearer"

def test_token_auth_failure():
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "admin", "password": "wrongpassword"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Usuário ou senha incorretos."

def test_secured_endpoint_without_token():
    response = client.get("/api/v1/kpis")
    assert response.status_code == 401

def test_secured_endpoint_with_invalid_token():
    response = client.get(
        "/api/v1/kpis",
        headers={"Authorization": "Bearer invalidtoken"}
    )
    assert response.status_code == 401
    assert "Token de autenticação inválido" in response.json()["detail"]

def test_secured_endpoint_with_valid_token():
    # Login to get valid token
    token_response = client.post(
        "/api/v1/auth/token",
        data={"username": "admin", "password": "adminpassword"}
    )
    token = token_response.json()["access_token"]
    
    # Request secured endpoint
    response = client.get(
        "/api/v1/kpis",
        headers={"Authorization": f"Bearer {token}"}
    )
    # If the database does not exist, it might raise 500/404, but not 401
    assert response.status_code != 401
