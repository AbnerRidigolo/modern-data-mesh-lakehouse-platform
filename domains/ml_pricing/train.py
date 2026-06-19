import os
import json
import logging
import duckdb
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_absolute_error
import joblib

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ML_Pricing_Training")

def train_model():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    db_path = os.environ.get("DB_PATH", os.path.join(base_dir, "storage", "analytics.duckdb"))
    model_dir = os.path.join(base_dir, "storage", "model_registry")
    
    os.makedirs(model_dir, exist_ok=True)
    
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
    
    # 1. Feature Preprocessing
    # One-hot encode product names to support multiple products in a single model
    df_encoded = pd.get_dummies(df, columns=["product_name"], prefix="prod", dtype=int)
    
    # Features and Target
    feature_cols = [c for c in df_encoded.columns if c.startswith("prod_") or c in ["price", "competitor_price", "day_of_week", "is_weekend"]]
    X = df_encoded[feature_cols]
    y = df_encoded["units_sold"]
    
    # 2. Train/Test Split & Fit
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    
    # 3. Evaluate Model
    y_pred = model.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)
    logger.info(f"Modelo treinado com sucesso. Test R2: {r2:.4f}, Test MAE: {mae:.4f}")
    
    # Save the model
    model_path = os.path.join(model_dir, "pricing_model.joblib")
    joblib.dump(model, model_path)
    logger.info(f"Modelo persistido no registro em: {model_path}")
    
    # 4. Optimization Loop (Revenue Maximization)
    optimal_pricing = {}
    
    # Reconstruct product list from one-hot features
    product_cols = [c for c in feature_cols if c.startswith("prod_")]
    unique_products = df["product_name"].unique()
    
    for prod_name in unique_products:
        prod_df = df[df["product_name"] == prod_name]
        avg_competitor = float(prod_df["competitor_price"].mean())
        base_price = float(prod_df["price"].median())
        
        # Test a range of prices around the base price (from 50% to 150% in steps of R$ 5.00)
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
                "day_of_week": 3,  # Midweek default
                "is_weekend": 0
            }
            # Set one-hot product flags
            for col in product_cols:
                row[col] = 1 if col == f"prod_{prod_name}" else 0
                
            opt_data.append(row)
            
        opt_df = pd.DataFrame(opt_data)
        # Ensure correct column ordering matching training
        opt_df = opt_df[feature_cols]
        
        # Predict demand (Q)
        predicted_demands = model.predict(opt_df)
        
        # Find price that maximizes Price * Q
        for i, p in enumerate(candidate_prices):
            q = predicted_demands[i]
            revenue = p * q
            if revenue > max_revenue:
                max_revenue = revenue
                best_price = p
                projected_demand_at_best = q
                
        # Current baseline revenue (median price * average daily units)
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

if __name__ == "__main__":
    train_model()
