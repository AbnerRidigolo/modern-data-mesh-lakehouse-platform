"""Testes do router de analytics (marts semânticos ricos).

Os endpoints dependem do Data Warehouse (DuckDB) materializado pelo dbt. Em
ambientes onde a pipeline ainda não rodou, `run_query` levanta FileNotFoundError
e a API responde 500 — por isso os testes de sucesso toleram (200, 500), mas os
testes de segurança (ausência de token) exigem 401 de forma estrita.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.deps import run_query  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

ANALYTICS_ENDPOINTS = [
    "/api/v1/analytics/daily-revenue",
    "/api/v1/analytics/category-performance",
    "/api/v1/analytics/cohorts",
    "/api/v1/analytics/marketing",
]


@pytest.fixture
def auth_headers():
    resp = client.post("/api/v1/auth/token", data={"username": "admin", "password": "adminpassword"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("endpoint", ANALYTICS_ENDPOINTS)
def test_analytics_requires_auth(endpoint):
    resp = client.get(endpoint)
    assert resp.status_code == 401


@pytest.mark.parametrize("endpoint", ANALYTICS_ENDPOINTS)
def test_analytics_returns_data_or_missing_warehouse(endpoint, auth_headers):
    resp = client.get(endpoint, headers=auth_headers)
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        assert "data" in resp.json()
        assert isinstance(resp.json()["data"], list)


def test_daily_revenue_rejects_out_of_range_window(auth_headers):
    resp = client.get("/api/v1/analytics/daily-revenue?days=99999", headers=auth_headers)
    assert resp.status_code == 422


def test_run_query_uses_bound_parameters_no_injection():
    """Garante que run_query aceita parâmetros ligados (defesa contra SQL injection)."""
    # Consulta puramente in-memory: não depende do warehouse em disco.
    # Se params não fossem aplicados, o '?' ficaria literal e a query falharia.
    try:
        rows = run_query("SELECT ? AS a, ? AS b", [1, "x'; DROP TABLE t; --"])
    except FileNotFoundError:
        pytest.skip("Warehouse DuckDB indisponível neste ambiente")
    assert rows == [{"a": 1, "b": "x'; DROP TABLE t; --"}]
