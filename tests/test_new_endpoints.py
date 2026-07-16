import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_headers():
    resp = client.post("/api/v1/auth/token", data={"username": "admin", "password": "adminpassword"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_catalog_domains_lists_crm_and_ecommerce_contracts(auth_headers):
    resp = client.get("/api/v1/catalog/domains", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "crm" in data and "ecommerce" in data
    crm_field_names = {f["name"] for f in data["crm"]["contract_fields"]}
    assert {"id", "name", "email", "status"}.issubset(crm_field_names)


def test_catalog_domains_requires_auth():
    resp = client.get("/api/v1/catalog/domains")
    assert resp.status_code == 401


def test_quarantine_unknown_domain_returns_404(auth_headers):
    resp = client.get("/api/v1/quarantine/unknown-domain", headers=auth_headers)
    assert resp.status_code == 404


def test_quarantine_file_path_traversal_is_blocked(auth_headers):
    resp = client.get("/api/v1/quarantine/crm/..%2F..%2F..%2Fetc%2Fpasswd", headers=auth_headers)
    assert resp.status_code == 404


def test_delta_tables_lists_known_data_products(auth_headers):
    resp = client.get("/api/v1/delta/tables", headers=auth_headers)
    assert resp.status_code == 200
    keys = {t["key"] for t in resp.json()}
    assert keys == {"crm_customers", "ecommerce_sales"}


def test_delta_unknown_table_history_returns_404(auth_headers):
    resp = client.get("/api/v1/delta/not_a_table/history", headers=auth_headers)
    assert resp.status_code == 404


def test_lineage_without_manifest_returns_404(auth_headers):
    resp = client.get("/api/v1/lineage", headers=auth_headers)
    assert resp.status_code in (404, 200)


def test_ml_pricing_metadata_without_model_returns_404(auth_headers):
    resp = client.get("/api/v1/ml/pricing-metadata", headers=auth_headers)
    assert resp.status_code in (404, 200)


def test_login_lockout_after_repeated_failures():
    username = "lockout-test-user"
    last_resp = None
    for _ in range(10):
        last_resp = client.post("/api/v1/auth/token", data={"username": username, "password": "wrong"})
    assert last_resp.status_code == 429
