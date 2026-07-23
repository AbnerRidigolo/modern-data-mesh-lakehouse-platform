"""Shared filesystem/storage path resolution for the platform.

Centralizes the local-vs-container-vs-S3 path logic that was previously
duplicated across app/main.py, domains/ml_pricing/*.py and portal.py.
"""
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

BUCKET_NAME = "lakehouse"


def s3_enabled() -> bool:
    return os.environ.get("AWS_ACCESS_KEY_ID") is not None


def get_db_path() -> str:
    """Resolve the DuckDB analytics database path (env override > container > local)."""
    db_path = os.environ.get("DB_PATH")
    if db_path:
        return db_path
    container_db = "/opt/airflow/storage/analytics.duckdb"
    local_db = os.path.join(BASE_DIR, "storage", "analytics.duckdb")
    return container_db if os.path.exists(container_db) else local_db


def get_model_dir() -> str:
    container_dir = "/opt/airflow/storage/model_registry"
    local_dir = os.path.join(BASE_DIR, "storage", "model_registry")
    return container_dir if os.path.exists(container_dir) else local_dir


def get_data_quality_dir() -> str:
    return os.path.join(BASE_DIR, "storage", "data_quality")


def get_logs_dir() -> str:
    return os.path.join(BASE_DIR, "storage", "logs")


def get_quarantine_dir(domain: str) -> str:
    return os.path.join(BASE_DIR, "storage", "raw", "quarantine", domain)


def get_dbt_manifest_path() -> str:
    return os.path.join(BASE_DIR, "analytics_dw", "target", "manifest.json")


def get_delta_storage_options() -> dict:
    return {
        "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"),
        "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin"),
        "AWS_ENDPOINT_URL": os.environ.get("MINIO_ENDPOINT_URL", "http://localhost:9000"),
        "AWS_ALLOW_HTTP": "true",
        "AWS_S3_ALLOW_UNSAFE_SSL": "true",
    }


# Domain -> relative table path segment, shared by ingestion writers and the API/portal readers.
DELTA_TABLES = {
    "crm_customers": ("crm", "customers"),
    "ecommerce_sales": ("ecommerce", "sales"),
    "marketing_campaigns": ("marketing", "campaigns"),
}


def get_delta_table_path(table_key: str) -> str:
    """Return the local or s3:// path for a known Delta table key (see DELTA_TABLES)."""
    domain, table = DELTA_TABLES[table_key]
    if s3_enabled():
        return f"s3://{BUCKET_NAME}/{domain}/{table}"
    return os.path.join(BASE_DIR, "storage", "lakehouse", domain, table)


def get_delta_read_options() -> dict | None:
    return get_delta_storage_options() if s3_enabled() else None
