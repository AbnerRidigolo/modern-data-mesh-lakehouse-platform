"""Testes do Feature Store — com foco na CORREÇÃO POINT-IN-TIME.

O teste central prova que o point-in-time join nunca vaza o futuro: um evento
no dia D recebe a feature vigente em D-1 (ou anterior), jamais a de D+k. Esse é
o requisito que distingue um feature store de verdade de um simples cache.
"""
import os
import sys

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from domains.feature_store.store import FeatureStore, load_registry


@pytest.fixture
def temp_store(tmp_path):
    """Feature store apontando para um DuckDB temporário com feature views sintéticas."""
    db_path = str(tmp_path / "fs_test.duckdb")
    conn = duckdb.connect(db_path)

    # ft_product_features sintética: valor da feature cresce a cada dia
    # (dia 1 -> 10, dia 2 -> 20, ...), para tornar o vazamento detectável.
    conn.execute("""
        CREATE TABLE ft_product_features AS
        SELECT * FROM (VALUES
            ('P1', DATE '2026-01-01', 10, 100.0),
            ('P1', DATE '2026-01-02', 20, 100.0),
            ('P1', DATE '2026-01-03', 30, 100.0),
            ('P1', DATE '2026-01-04', 40, 100.0),
            ('P2', DATE '2026-01-02', 99, 200.0)
        ) AS t(product_name, feature_date, units_30d, avg_price_30d)
    """)
    conn.execute("""
        CREATE TABLE ft_customer_features AS
        SELECT * FROM (VALUES
            (1, TIMESTAMP '2026-01-03 12:00:00', 5, 500.0, 'Champion'),
            (2, TIMESTAMP '2026-01-01 09:00:00', 1, 50.0, 'Regular')
        ) AS t(customer_id, feature_timestamp, orders_90d, revenue_90d, rfm_segment)
    """)
    conn.close()

    registry = {
        "entities": {
            "product": {"join_key": "product_name", "description": "produto"},
            "customer": {"join_key": "customer_id", "description": "cliente"},
        },
        "feature_views": {
            "product_demand": {
                "entity": "product",
                "source_table": "ft_product_features",
                "timestamp_field": "feature_date",
                "online_ttl_seconds": 86400,
                "owner": "Test",
                "description": "test view",
                "features": [
                    {"name": "units_30d", "dtype": "int", "description": "u"},
                    {"name": "avg_price_30d", "dtype": "float", "description": "p"},
                ],
            },
            "customer_activity": {
                "entity": "customer",
                "source_table": "ft_customer_features",
                "timestamp_field": "feature_timestamp",
                "online_ttl_seconds": 86400,
                "owner": "Test",
                "description": "test view",
                "features": [
                    {"name": "orders_90d", "dtype": "int", "description": "o"},
                    {"name": "revenue_90d", "dtype": "float", "description": "r"},
                    {"name": "rfm_segment", "dtype": "str", "description": "s"},
                ],
            },
        },
    }
    import yaml

    reg_path = tmp_path / "registry.yml"
    reg_path.write_text(yaml.safe_dump(registry))
    return FeatureStore(registry_path=str(reg_path), redis_client=None, db_path=db_path)


class TestPointInTimeCorrectness:
    """O núcleo: nenhum vazamento de futuro no join histórico."""

    def test_event_gets_feature_from_same_or_past_never_future(self, temp_store):
        # Evento em 03/01 deve pegar a feature de 03/01 (30), não a de 04/01 (40)
        spine = pd.DataFrame({
            "product_name": ["P1"],
            "event_timestamp": ["2026-01-03"],
        })
        result = temp_store.get_historical_features("product_demand", spine)
        assert result.iloc[0]["units_30d"] == 30

    def test_event_between_feature_dates_uses_last_known(self, temp_store):
        # Evento às 06:00 de 02/01 — a feature de 02/01 tem timestamp de data (00:00),
        # então <= vale; deve pegar 20 (de 02/01), nunca 30 (03/01).
        spine = pd.DataFrame({
            "product_name": ["P1"],
            "event_timestamp": ["2026-01-02 06:00:00"],
        })
        result = temp_store.get_historical_features("product_demand", spine)
        assert result.iloc[0]["units_30d"] == 20

    def test_event_before_any_feature_gets_null(self, temp_store):
        # Evento em 2025 — não existe feature anterior; ASOF LEFT JOIN retorna NULL
        spine = pd.DataFrame({
            "product_name": ["P1"],
            "event_timestamp": ["2025-12-31"],
        })
        result = temp_store.get_historical_features("product_demand", spine)
        assert pd.isna(result.iloc[0]["units_30d"])

    def test_multiple_events_each_get_correct_snapshot(self, temp_store):
        # Prova em lote: cada evento recebe exatamente a feature do seu dia
        spine = pd.DataFrame({
            "product_name": ["P1", "P1", "P1"],
            "event_timestamp": ["2026-01-01", "2026-01-02", "2026-01-04"],
        })
        result = temp_store.get_historical_features("product_demand", spine).sort_values("event_timestamp")
        assert list(result["units_30d"]) == [10, 20, 40]

    def test_join_key_isolation(self, temp_store):
        # A feature de P2 (99) nunca vaza para eventos de P1
        spine = pd.DataFrame({"product_name": ["P1"], "event_timestamp": ["2026-01-04"]})
        result = temp_store.get_historical_features("product_demand", spine)
        assert result.iloc[0]["units_30d"] == 40

    def test_requires_join_key_and_timestamp_columns(self, temp_store):
        with pytest.raises(ValueError, match="precisa das colunas"):
            temp_store.get_historical_features("product_demand", pd.DataFrame({"foo": [1]}))


class TestOnlineStore:
    def test_materialize_writes_latest_snapshot(self, temp_store):
        report = temp_store.materialize()
        assert report["product_demand"]["entities_written"] == 2
        assert report["customer_activity"]["entities_written"] == 2
        assert report["product_demand"]["backend"] == "in_memory"

    def test_online_lookup_returns_latest(self, temp_store):
        temp_store.materialize()
        # P1 tem 4 dias; o online store serve a última (04/01 -> 40)
        result = temp_store.get_online_features("product_demand", "P1")
        assert result["features"]["units_30d"] == 40
        assert result["source"] == "online_memory"

    def test_online_fallback_to_offline_when_not_materialized(self, temp_store):
        # Sem materializar: cai no offline store (linha mais recente)
        result = temp_store.get_online_features("customer_activity", 1)
        assert result["source"] == "offline_fallback"
        assert result["features"]["rfm_segment"] == "Champion"

    def test_online_not_found(self, temp_store):
        result = temp_store.get_online_features("product_demand", "INEXISTENTE")
        assert result["source"] == "not_found"
        assert result["features"] is None


class TestRegistryAndFreshness:
    def test_catalog_exposes_governance(self, temp_store):
        catalog = temp_store.catalog()
        assert set(catalog["entities"]) == {"product", "customer"}
        assert catalog["feature_views"]["product_demand"]["owner"] == "Test"
        assert len(catalog["feature_views"]["customer_activity"]["features"]) == 3

    def test_freshness_reports_age_and_staleness(self, temp_store):
        fresh = {f["feature_view"]: f for f in temp_store.freshness()}
        assert fresh["product_demand"]["rows"] == 5
        # Timestamps de 2026-01 são antigos -> stale
        assert fresh["product_demand"]["is_stale"] is True
        assert fresh["product_demand"]["age_hours"] > 0

    def test_unknown_view_raises(self, temp_store):
        with pytest.raises(KeyError):
            temp_store.get_online_features("view_inexistente", "x")


class TestRealRegistry:
    def test_shipped_registry_is_valid(self):
        # O registry de produção precisa carregar e ter as duas views esperadas
        registry = load_registry()
        assert "product_demand" in registry["feature_views"]
        assert "customer_activity" in registry["feature_views"]
        assert registry["entities"]["product"]["join_key"] == "product_name"
        assert registry["entities"]["customer"]["join_key"] == "customer_id"
