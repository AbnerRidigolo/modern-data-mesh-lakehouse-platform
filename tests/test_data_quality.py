"""Testes unitários do motor de Data Quality (domains/ml_pricing/data_quality.py).

Cada check é exercitado contra um DuckDB em memória com cenários controlados
de aprovação e violação, sem depender do pipeline completo.
"""
import os
import sys

import duckdb
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from domains.ml_pricing.data_quality import (
    check_competitor_price,
    check_orphan_records,
    check_sales_drop,
    check_volume_anomaly,
)


@pytest.fixture
def conn():
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE fct_sales (
            sale_id INT,
            customer_id INT,
            customer_name VARCHAR,
            product_name VARCHAR,
            amount DOUBLE,
            competitor_price DOUBLE,
            status VARCHAR,
            sale_date TIMESTAMP
        )
    """)
    yield conn
    conn.close()


def _insert_sale(conn, sale_id, product, amount, competitor_price, status="COMPLETED",
                 days_ago=0, customer_name="Cliente Teste"):
    conn.execute(
        "INSERT INTO fct_sales VALUES (?, 1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP - INTERVAL (?) DAY)",
        [sale_id, customer_name, product, amount, competitor_price, status, days_ago],
    )


class TestCompetitorPrice:
    def test_passes_when_prices_are_close(self, conn):
        _insert_sale(conn, 1, "Produto A", 100.0, 95.0)
        status, metric, _, details = check_competitor_price(conn)
        assert status == "Passed"
        assert metric == 0.0
        assert details == []

    def test_fails_when_competitor_deviates_over_50pct(self, conn):
        _insert_sale(conn, 1, "Produto A", 100.0, 300.0)
        status, metric, _, details = check_competitor_price(conn)
        assert status == "Failed"
        assert metric == 1.0
        assert len(details) == 1


class TestSalesDrop:
    def test_passes_when_all_products_sold_recently(self, conn):
        _insert_sale(conn, 1, "Produto A", 100.0, 100.0, days_ago=1)
        status, metric, _, _ = check_sales_drop(conn)
        assert status == "Passed"
        assert metric == 0.0

    def test_fails_when_product_has_no_recent_sales(self, conn):
        _insert_sale(conn, 1, "Produto Antigo", 100.0, 100.0, days_ago=30)
        _insert_sale(conn, 2, "Produto Ativo", 50.0, 50.0, days_ago=1)
        status, metric, _, details = check_sales_drop(conn)
        assert status == "Failed"
        assert metric == 1.0
        assert "Produto Antigo" in details[0]


class TestOrphanRecords:
    def test_passes_with_no_orphans(self, conn):
        _insert_sale(conn, 1, "Produto A", 100.0, 100.0)
        status, metric, _, _ = check_orphan_records(conn)
        assert status == "Passed"
        assert metric == 0.0

    def test_passes_on_empty_table(self, conn):
        status, _, _, _ = check_orphan_records(conn)
        assert status == "Passed"

    def test_fails_when_orphan_ratio_exceeds_5pct(self, conn):
        _insert_sale(conn, 1, "Produto A", 100.0, 100.0, customer_name="Desconhecido (Órfão)")
        for i in range(2, 6):
            _insert_sale(conn, i, "Produto A", 100.0, 100.0)
        status, metric, _, _ = check_orphan_records(conn)
        assert status == "Failed"
        assert metric == 20.0


class TestVolumeAnomaly:
    def test_passes_with_stable_volume(self, conn):
        sale_id = 0
        for day in range(10, 0, -1):
            for _ in range(5):
                sale_id += 1
                _insert_sale(conn, sale_id, "Produto A", 100.0, 100.0, days_ago=day)
        status, metric, _, _ = check_volume_anomaly(conn)
        assert status == "Passed"
        assert metric == 5.0

    def test_fails_on_volume_spike(self, conn):
        sale_id = 0
        # Histórico estável de 5 vendas/dia com leve variação, e um pico de 60 no último dia
        for day in range(15, 0, -1):
            daily = 5 + (day % 2)
            for _ in range(daily):
                sale_id += 1
                _insert_sale(conn, sale_id, "Produto A", 100.0, 100.0, days_ago=day)
        for _ in range(60):
            sale_id += 1
            _insert_sale(conn, sale_id, "Produto A", 100.0, 100.0, days_ago=0)
        status, metric, _, _ = check_volume_anomaly(conn)
        assert status == "Failed"
        assert metric == 60.0
