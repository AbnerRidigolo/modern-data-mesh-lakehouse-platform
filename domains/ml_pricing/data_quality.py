import datetime
import json
import logging
import os

import duckdb

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Data_Quality_Check")

def run_test(conn, test_id, name, description, query_fn):
    logger.info(f"Executando teste: {name}...")
    try:
        status, metric_value, threshold, details = query_fn(conn)
        logger.info(f"Resultado {test_id}: {status} (Métrica: {metric_value}, Limite: {threshold})")
        return {
            "test_id": test_id,
            "name": name,
            "description": description,
            "status": status,
            "metric_value": metric_value,
            "threshold": threshold,
            "details": details
        }
    except Exception as e:
        logger.error(f"Erro ao executar teste {test_id}: {e}")
        return {
            "test_id": test_id,
            "name": name,
            "description": description,
            "status": "Failed",
            "metric_value": 0.0,
            "threshold": "Error",
            "details": f"Erro de execução: {str(e)}"
        }

# --- Assertion Functions ---

def check_competitor_price(conn):
    # Alert if competitor price fluctuates more than 50% from amount
    query = """
    SELECT sale_id, product_name, amount, competitor_price,
           ROUND(ABS(competitor_price - amount) / amount * 100, 2) as diff_pct
    FROM fct_sales
    WHERE status = 'COMPLETED'
      AND ABS(competitor_price - amount) / amount > 0.5
    LIMIT 10;
    """
    rows = conn.execute(query).fetchall()

    total_violations = len(rows)
    status = "Passed" if total_violations == 0 else "Failed"
    details = []
    for r in rows:
        details.append(f"Venda ID {r[0]}: {r[1]} preço R$ {r[2]} vs Concorrente R$ {r[3]} ({r[4]}% dif)")

    return status, float(total_violations), "0 violações (limite 50% dif)", details

def check_sales_drop(conn):
    # Check if any product has 0 sales in the last 3 days
    # First get list of all historical products in completed sales
    all_products = [r[0] for r in conn.execute("SELECT DISTINCT product_name FROM fct_sales").fetchall()]

    # Get sales count in the last 3 days
    query = """
    SELECT product_name, COUNT(*) as sales_count
    FROM fct_sales
    WHERE status = 'COMPLETED'
      AND sale_date >= CURRENT_DATE - INTERVAL '3' DAY
    GROUP BY product_name;
    """
    rows = conn.execute(query).fetchall()
    sales_map = {r[0]: r[1] for r in rows}

    zero_sales_products = []
    for prod in all_products:
        if sales_map.get(prod, 0) == 0:
            zero_sales_products.append(prod)

    total_failed = len(zero_sales_products)
    status = "Passed" if total_failed == 0 else "Failed"
    details = [f"Produtos sem vendas nos últimos 3 dias: {', '.join(zero_sales_products)}"] if zero_sales_products else []

    return status, float(total_failed), "0 produtos com vendas zeradas", details

def check_orphan_records(conn):
    # Check percentage of orphan joins (customer_name is 'Desconhecido (Órfão)')
    total_sales = conn.execute("SELECT COUNT(*) FROM fct_sales").fetchone()[0]
    if total_sales == 0:
        return "Passed", 0.0, "< 5% órfãos", ["Tabela fct_sales vazia"]

    orphans = conn.execute("SELECT COUNT(*) FROM fct_sales WHERE customer_name = 'Desconhecido (Órfão)'").fetchone()[0]
    pct = (orphans / total_sales) * 100

    status = "Passed" if pct < 5.0 else "Failed"
    details = [f"Encontrados {orphans} registros órfãos de um total de {total_sales} vendas ({pct:.2f}%)"]

    return status, round(pct, 2), "< 5% de órfãos", details

def check_volume_anomaly(conn):
    # Check if the volume of the latest day is outside mean +/- 2*stddev
    # 1. Get daily sales counts
    daily_sales = conn.execute("""
        WITH daily_sales AS (
            SELECT CAST(sale_date AS DATE) as s_date, COUNT(*) as daily_count
            FROM fct_sales
            WHERE status = 'COMPLETED'
            GROUP BY 1
        )
        SELECT AVG(daily_count), STDDEV(daily_count) FROM daily_sales;
    """).fetchone()

    avg_vol = daily_sales[0] or 0.0
    std_vol = daily_sales[1] or 0.0

    # 2. Get latest day volume
    latest_vol_row = conn.execute("""
        SELECT COUNT(*)
        FROM fct_sales
        WHERE status = 'COMPLETED'
          AND CAST(sale_date AS DATE) = (SELECT MAX(CAST(sale_date AS DATE)) FROM fct_sales);
    """).fetchone()

    latest_vol = latest_vol_row[0] if latest_vol_row else 0.0

    # Check bounds
    lower_bound = max(0, avg_vol - 2 * std_vol)
    upper_bound = avg_vol + 2 * std_vol

    status = "Passed"
    if std_vol > 0:
        if latest_vol < lower_bound or latest_vol > upper_bound:
            status = "Failed"

    details = [f"Volume do último dia: {latest_vol} | Média histórica: {avg_vol:.2f} (Intervalo esperado: {lower_bound:.1f} a {upper_bound:.1f})"]

    return status, float(latest_vol), f"Entre {lower_bound:.1f} e {upper_bound:.1f}", details

def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    local_db = os.path.join(base_dir, "storage", "analytics.duckdb")
    container_db = "/opt/airflow/storage/analytics.duckdb"

    db_path = os.environ.get("DB_PATH")
    if not db_path:
        db_path = container_db if os.path.exists(container_db) else local_db

    logger.info(f"Iniciando checagens de Data Quality no DuckDB em: {db_path}")

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Arquivo do DuckDB não encontrado em {db_path}. Execute a pipeline primeiro.")

    conn = duckdb.connect(db_path, read_only=True)
    tests_results = []

    try:
        tests_results.append(run_test(conn, "DQ_01", "Desvio de Preço Concorrente", "Alerta se o preço do concorrente flutuar mais de 50% do nosso preço", check_competitor_price))
        tests_results.append(run_test(conn, "DQ_02", "Anomalia de Queda de Vendas", "Alerta se algum produto tiver vendas zeradas nos últimos 3 dias", check_sales_drop))
        tests_results.append(run_test(conn, "DQ_03", "Registros Órfãos (Completeness)", "Alerta se a proporção de clientes órfãos na fato for maior que 5%", check_orphan_records))
        tests_results.append(run_test(conn, "DQ_04", "Anomalia de Volume Diário", "Alerta se o volume diário de vendas do último dia desviar mais que 2 desvios padrões", check_volume_anomaly))
    finally:
        conn.close()

    # Summarize results
    total_tests = len(tests_results)
    passed_tests = sum(1 for t in tests_results if t["status"] == "Passed")
    failed_tests = total_tests - passed_tests
    compliance_score = (passed_tests / total_tests) * 100

    report = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "failed_tests": failed_tests,
        "compliance_score": round(compliance_score, 2),
        "status": "Passed" if failed_tests == 0 else "Failed",
        "tests": tests_results
    }

    # Save Report
    dq_dir = os.path.join(base_dir, "storage", "data_quality")
    os.makedirs(dq_dir, exist_ok=True)

    report_file = os.path.join(dq_dir, "dq_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # Append to History (maximum 100 records for display history)
    history_file = os.path.join(dq_dir, "dq_history.jsonl")
    history_entry = {
        "timestamp": report["timestamp"],
        "compliance_score": report["compliance_score"],
        "passed_tests": report["passed_tests"],
        "failed_tests": report["failed_tests"],
        "total_tests": report["total_tests"],
        "status": report["status"]
    }
    with open(history_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(history_entry) + "\n")

    logger.info(f"Relatório de Data Quality salvo! Score: {compliance_score:.2f}% | Status geral: {report['status']}")

if __name__ == "__main__":
    main()
