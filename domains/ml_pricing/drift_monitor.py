import os
import json
import logging
import duckdb
import pandas as pd
from datetime import datetime
from scipy.stats import ks_2samp

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Drift_Monitor")

def check_drift():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    db_path = os.environ.get("DB_PATH", os.path.join(base_dir, "storage", "analytics.duckdb"))
    model_dir = os.path.join(base_dir, "storage", "model_registry")
    
    os.makedirs(model_dir, exist_ok=True)
    
    logger.info(f"Conectando ao DuckDB para análise de drift: {db_path}")
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Banco de dados DuckDB não encontrado em: {db_path}")
        
    conn = duckdb.connect(db_path, read_only=True)
    try:
        # Load all sales prices by product
        df_all = conn.execute("SELECT product_name, price, sale_date FROM ml_features_pricing").fetchdf()
    finally:
        conn.close()
        
    if df_all.empty:
        logger.warning("Nenhum dado encontrado para verificar drift.")
        return
        
    df_all["sale_date"] = pd.to_datetime(df_all["sale_date"])
    max_date = df_all["sale_date"].max()
    
    # We define "current" as the last 15 days of data, and "baseline" as everything prior
    cutoff_date = max_date - pd.Timedelta(days=15)
    
    drift_report = {}
    overall_drift_detected = False
    
    unique_products = df_all["product_name"].unique()
    for prod in unique_products:
        prod_df = df_all[df_all["product_name"] == prod]
        
        baseline_prices = prod_df[prod_df["sale_date"] < cutoff_date]["price"].values
        current_prices = prod_df[prod_df["sale_date"] >= cutoff_date]["price"].values
        
        # We need sufficient samples in both sets to perform the test
        if len(baseline_prices) < 10 or len(current_prices) < 5:
            logger.info(f"Amostra insuficiente para {prod} (Baseline: {len(baseline_prices)}, Atual: {len(current_prices)}). Pulando.")
            drift_report[prod] = {
                "status": "insufficient_data",
                "p_value": 1.0,
                "ks_stat": 0.0,
                "message": f"Amostras insuficientes (Baseline: {len(baseline_prices)}, Atual: {len(current_prices)})"
            }
            continue
            
        # Run KS test
        ks_stat, p_value = ks_2samp(baseline_prices, current_prices)
        
        # If p-value < 0.05, distributions are statistically different
        drift_detected = bool(p_value < 0.05)
        if drift_detected:
            overall_drift_detected = True
            
        drift_report[prod] = {
            "status": "drift_detected" if drift_detected else "stable",
            "p_value": round(float(p_value), 4),
            "ks_stat": round(float(ks_stat), 4),
            "baseline_count": len(baseline_prices),
            "current_count": len(current_prices)
        }
        logger.info(f"Drift check {prod}: Status={drift_report[prod]['status']}, p-value={p_value:.4f}")
        
    report = {
        "overall_drift_detected": overall_drift_detected,
        "checked_at": datetime.now().isoformat(),
        "products": drift_report
    }
    
    report_path = os.path.join(model_dir, "drift_status.json")
    with open(report_path, "w", encoding="utf-8") as rf:
        json.dump(report, rf, indent=2)
        
    logger.info(f"Relatório de drift salvo em: {report_path}")

if __name__ == "__main__":
    check_drift()
