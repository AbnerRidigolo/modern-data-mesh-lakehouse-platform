import argparse
import json
import logging
import os
from datetime import datetime

import duckdb
import joblib
import numpy as np
import pandas as pd
from deltalake import DeltaTable
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

# Configure MLflow import safely
try:
    import mlflow
    import mlflow.sklearn
except ImportError:
    mlflow = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ML_Pricing_Training")

def train_model(sales_version: int = None, customers_version: int = None):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    db_path = os.environ.get("DB_PATH", os.path.join(base_dir, "storage", "analytics.duckdb"))
    model_dir = os.path.join(base_dir, "storage", "model_registry")

    os.makedirs(model_dir, exist_ok=True)

    # Configure MLflow
    mlflow_enabled = False
    if mlflow is not None:
        mlflow_tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
        mlflow.set_tracking_uri(mlflow_tracking_uri)
        try:
            mlflow.set_experiment("Dynamic Pricing Optimization")
            mlflow_enabled = True
            logger.info(f"MLflow conectado com sucesso em: {mlflow_tracking_uri}")
        except Exception as e:
            logger.warning(f"Servidor MLflow inacessível em {mlflow_tracking_uri}: {e}. Rodando sem logs MLflow.")

    # 1. Feature Preprocessing
    # Load dataset depending on whether Delta Time Travel is enabled
    if sales_version is not None or customers_version is not None:
        logger.info(f"Modo Time Travel Ativado. Sales Version: {sales_version}, Customers Version: {customers_version}")
        customers_delta_path = os.path.join(base_dir, "storage", "lakehouse", "crm", "customers")
        sales_delta_path = os.path.join(base_dir, "storage", "lakehouse", "ecommerce", "sales")

        try:
            # Load specific versions
            dt_cust = DeltaTable(customers_delta_path, version=customers_version) if customers_version is not None else DeltaTable(customers_delta_path)
            dt_sales = DeltaTable(sales_delta_path, version=sales_version) if sales_version is not None else DeltaTable(sales_delta_path)

            customers_raw = dt_cust.to_pandas()
            sales_raw = dt_sales.to_pandas()

            # Connect to in-memory DuckDB and register DataFrames
            conn = duckdb.connect()
            conn.register("customers_raw", customers_raw)
            conn.register("sales_raw", sales_raw)

            # Recreate views using SQL
            conn.execute("""
            CREATE OR REPLACE TEMPORARY VIEW stg_customers AS
            SELECT
                CAST(id AS INT) AS customer_id,
                TRIM(name) AS customer_name,
                LOWER(email) AS email,
                CAST(created_at AS TIMESTAMP) AS created_at,
                LOWER(status) AS status
            FROM customers_raw;
            """)

            conn.execute("""
            CREATE OR REPLACE TEMPORARY VIEW stg_sales AS
            SELECT
                CAST(sale_id AS INT) AS sale_id,
                CAST(customer_id AS INT) AS customer_id,
                TRIM(product) AS product_name,
                CAST(amount AS DOUBLE) AS amount,
                CAST(competitor_price AS DOUBLE) AS competitor_price,
                UPPER(status) AS status,
                CAST(sale_date AS TIMESTAMP) AS sale_date
            FROM sales_raw;
            """)

            conn.execute("""
            CREATE OR REPLACE TEMPORARY VIEW dim_customers AS
            WITH customers AS (
                SELECT * FROM stg_customers
            ),
            deduped AS (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at DESC) as rn
                FROM customers
            )
            SELECT
                customer_id,
                customer_name,
                email,
                created_at,
                status,
                CASE WHEN status = 'active' THEN 1 ELSE 0 END AS is_active_flag
            FROM deduped
            WHERE rn = 1;
            """)

            conn.execute("""
            CREATE OR REPLACE TEMPORARY VIEW fct_sales AS
            WITH sales AS (
                SELECT * FROM stg_sales
            ),
            deduped_sales AS (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY sale_id ORDER BY sale_date DESC) as rn
                FROM sales
            ),
            customers AS (
                SELECT * FROM dim_customers
            )
            SELECT
                s.sale_id,
                s.customer_id,
                COALESCE(c.customer_name, 'Desconhecido (Órfão)') AS customer_name,
                s.product_name,
                s.amount,
                s.competitor_price,
                s.status,
                s.sale_date,
                CASE WHEN c.customer_id IS NULL THEN 1 ELSE 0 END AS is_orphan_join
            FROM deduped_sales s
            LEFT JOIN customers c ON s.customer_id = c.customer_id
            WHERE s.rn = 1;
            """)

            df = conn.execute("""
            WITH completed_sales AS (
                SELECT *
                FROM fct_sales
                WHERE status = 'COMPLETED'
            ),
            daily_aggregation AS (
                SELECT
                    product_name,
                    CAST(sale_date AS DATE) AS sale_date,
                    amount AS price,
                    AVG(competitor_price) AS competitor_price,
                    COUNT(*) AS units_sold,
                    SUM(amount) AS total_revenue
                FROM completed_sales
                GROUP BY 1, 2, 3
            )
            SELECT
                product_name,
                sale_date,
                price,
                COALESCE(competitor_price, price) AS competitor_price,
                units_sold,
                total_revenue,
                EXTRACT(dow FROM sale_date) AS day_of_week,
                CASE WHEN EXTRACT(dow FROM sale_date) IN (0, 6) THEN 1 ELSE 0 END AS is_weekend
            FROM daily_aggregation;
            """).fetchdf()

            conn.close()
        except Exception as e:
            logger.error(f"Erro ao extrair dados no modo Time Travel: {e}")
            raise e
    else:
        logger.info(f"Conectando ao DuckDB para extração de features: {db_path}")
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Banco de dados DuckDB não encontrado em: {db_path}")

        conn = duckdb.connect(db_path, read_only=True)
        try:
            df = conn.execute("SELECT * FROM ml_features_pricing").fetchdf()
        finally:
            conn.close()

    if df.empty:
        logger.warning("Tabela ml_features_pricing vazia. Abortando treinamento.")
        return

    logger.info(f"Dados carregados. Registros extraídos: {len(df)}")

    # One-hot encode product names
    df_encoded = pd.get_dummies(df, columns=["product_name"], prefix="prod", dtype=int)

    # Features and Target
    feature_cols = [c for c in df_encoded.columns if c.startswith("prod_") or c in ["price", "competitor_price", "day_of_week", "is_weekend"]]
    X = df_encoded[feature_cols]
    y = df_encoded["units_sold"]

    # 2. Train/Test Split & Fit
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    n_estimators = 100
    random_state = 42

    # Start MLflow run
    if mlflow_enabled:
        try:
            mlflow.start_run()
            mlflow.log_param("n_estimators", n_estimators)
            mlflow.log_param("random_state", random_state)
            mlflow.log_param("test_size", 0.2)
            if sales_version is not None:
                mlflow.log_param("sales_delta_version", sales_version)
            if customers_version is not None:
                mlflow.log_param("customers_delta_version", customers_version)
        except Exception as e:
            logger.warning(f"Erro ao iniciar MLflow run: {e}")
            mlflow_enabled = False

    model = RandomForestRegressor(n_estimators=n_estimators, random_state=random_state)
    model.fit(X_train, y_train)

    # 3. Evaluate Model
    y_pred = model.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)
    logger.info(f"Modelo treinado. Test R2: {r2:.4f}, Test MAE: {mae:.4f}")

    if mlflow_enabled:
        try:
            mlflow.log_metric("r2_score", r2)
            mlflow.log_metric("mae", mae)
            mlflow.sklearn.log_model(model, "model", registered_model_name="pricing_random_forest")
            logger.info("Métricas e modelo logados no MLflow.")
        except Exception as e:
            logger.warning(f"Erro ao logar métricas/modelo no MLflow: {e}")

    # Save the model locally as a fallback
    model_path = os.path.join(model_dir, "pricing_model.joblib")
    joblib.dump(model, model_path)
    logger.info(f"Modelo persistido localmente em: {model_path}")

    # 4. Optimization Loop (Revenue Maximization)
    optimal_pricing = {}
    product_cols = [c for c in feature_cols if c.startswith("prod_")]
    unique_products = df["product_name"].unique()

    for prod_name in unique_products:
        prod_df = df[df["product_name"] == prod_name]
        avg_competitor = float(prod_df["competitor_price"].mean())
        base_price = float(prod_df["price"].median())

        # Test a range of prices around the base price
        min_test_price = max(10.0, base_price * 0.5)
        max_test_price = base_price * 1.5
        candidate_prices = np.arange(min_test_price, max_test_price, 5.0)

        best_price = base_price
        max_revenue = 0.0
        projected_demand_at_best = 0.0

        # Create features for each candidate price
        opt_data = []
        for p in candidate_prices:
            row = {
                "price": p,
                "competitor_price": avg_competitor,
                "day_of_week": 3,
                "is_weekend": 0
            }
            for col in product_cols:
                row[col] = 1 if col == f"prod_{prod_name}" else 0
            opt_data.append(row)

        opt_df = pd.DataFrame(opt_data)[feature_cols]
        predicted_demands = model.predict(opt_df)

        for i, p in enumerate(candidate_prices):
            q = predicted_demands[i]
            revenue = p * q
            if revenue > max_revenue:
                max_revenue = revenue
                best_price = p
                projected_demand_at_best = q

        avg_daily_units = float(prod_df["units_sold"].mean())
        current_revenue = base_price * avg_daily_units
        revenue_lift_pct = ((max_revenue - current_revenue) / current_revenue) * 100 if current_revenue > 0 else 0.0

        optimal_pricing[prod_name] = {
            "base_price": round(base_price, 2),
            "optimal_price": round(float(best_price), 2),
            "competitor_price": round(avg_competitor, 2),
            "expected_daily_demand": round(float(projected_demand_at_best), 2),
            "projected_daily_revenue": round(float(max_revenue), 2),
            "current_daily_revenue": round(float(current_revenue), 2),
            "revenue_lift_pct": round(float(revenue_lift_pct), 2)
        }

        logger.info(f"Otimização {prod_name}: Base: R$ {base_price:.2f} -> Ótimo: R$ {best_price:.2f} | Lift: {revenue_lift_pct:.2f}%")

    # 5. Save metadata and optimization results to JSON
    metadata = {
        "model_metrics": {
            "r2_score": round(r2, 4),
            "mae": round(mae, 4)
        },
        "feature_columns": feature_cols,
        "product_one_hot_columns": product_cols,
        "optimal_prices": optimal_pricing,
        "last_trained": datetime.now().isoformat()
    }

    metadata_path = os.path.join(model_dir, "pricing_metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as mf:
        json.dump(metadata, mf, indent=2)

    logger.info(f"Metadados de precificação persistidos em: {metadata_path}")

    if mlflow_enabled:
        try:
            # Log pricing metadata as artifact in MLflow
            mlflow.log_artifact(metadata_path)
            mlflow.end_run()
        except Exception as e:
            logger.warning(f"Erro ao encerrar run do MLflow: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sales-version", type=int, default=None, help="Versão da tabela de vendas do Delta Lake")
    parser.add_argument("--customers-version", type=int, default=None, help="Versão da tabela de clientes do Delta Lake")
    args = parser.parse_args()

    train_model(sales_version=args.sales_version, customers_version=args.customers_version)
