"""Treinamento do modelo de precificação dinâmica — pipeline com rigor estatístico.

Decisões de modelagem (racional de cientista de dados sênior):

1. **Validação temporal, nunca aleatória**: dados de demanda são uma série
   temporal — um split aleatório vaza o futuro para o treino e infla as
   métricas. O holdout são os últimos ``HOLDOUT_DAYS`` dias e a seleção de
   modelo usa ``TimeSeriesSplit`` (treina no passado, valida no futuro).
2. **Baseline obrigatório**: a mediana de demanda por produto. Um modelo que
   não bate um baseline trivial não merece ir para produção — o lift sobre o
   baseline é registrado na metadata.
3. **Restrições de monotonicidade**: conhecimento de domínio (demanda não
   cresce quando o preço sobe) é imposto ao HistGradientBoosting via
   ``monotonic_cst`` — evita curvas de elasticidade economicamente absurdas
   que um modelo puramente estatístico pode aprender de ruído.
4. **Métricas de negócio**: além de R²/MAE, WAPE (erro absoluto ponderado —
   robusto para demandas próximas de zero) e RMSE.
5. **Sanity check de elasticidade**: após o treino, verifica-se para cada
   produto se a curva preço→demanda do campeão é não-crescente.
6. **Sem training-serving skew**: features construídas por
   ``domains.ml_pricing.features`` — o mesmo módulo usado pelo endpoint de
   simulação da API.
"""
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
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

try:
    from .features import build_feature_row, build_training_frame, monotonic_constraints
except ImportError:
    from features import build_feature_row, build_training_frame, monotonic_constraints

try:
    import mlflow
    import mlflow.sklearn
except ImportError:
    mlflow = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ML_Pricing_Training")

HOLDOUT_DAYS = 14
CV_SPLITS = 4
RANDOM_STATE = 42
# Fração mínima de produtos com curva preço→demanda não-crescente para um
# candidato ser elegível a campeão. O otimizador consulta o modelo em preços
# contrafactuais (fora da distribuição observada); um modelo com WAPE
# ligeiramente melhor mas elasticidade economicamente inválida recomendaria
# preços absurdos — validade econômica é critério de seleção, não só erro.
ELASTICITY_GATE = 0.8


class ProductMedianBaseline:
    """Baseline ingênuo: prevê a mediana histórica de unidades por produto.

    É o piso de qualidade — qualquer modelo de verdade precisa superá-lo.
    """

    def __init__(self, product_columns: list[str]):
        self.product_columns = product_columns
        self.medians_: dict[str, float] = {}
        self.global_median_: float = 0.0

    def fit(self, X: pd.DataFrame, y: pd.Series):
        self.global_median_ = float(np.median(y))
        for col in self.product_columns:
            mask = X[col] == 1
            self.medians_[col] = float(np.median(y[mask])) if mask.any() else self.global_median_
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        preds = np.full(len(X), self.global_median_)
        for col in self.product_columns:
            mask = (X[col] == 1).to_numpy()
            preds[mask] = self.medians_[col]
        return preds


def wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Weighted Absolute Percentage Error: sum|erro| / sum|real|."""
    denom = np.abs(np.asarray(y_true)).sum()
    if denom == 0:
        return 0.0
    return float(np.abs(np.asarray(y_true) - np.asarray(y_pred)).sum() / denom)


def compute_metrics(y_true, y_pred) -> dict:
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "rmse": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 4),
        "wape": round(wape(y_true, y_pred), 4),
        "r2_score": round(float(r2_score(y_true, y_pred)), 4),
    }


def temporal_split(df: pd.DataFrame, holdout_days: int = HOLDOUT_DAYS) -> tuple[pd.Index, pd.Index]:
    """Índices de treino/holdout: holdout = últimos ``holdout_days`` dias de dados."""
    dates = pd.to_datetime(df["sale_date"])
    cutoff = dates.max() - pd.Timedelta(days=holdout_days)
    train_idx = df.index[dates <= cutoff]
    test_idx = df.index[dates > cutoff]
    return train_idx, test_idx


def build_candidates(feature_columns: list[str], product_columns: list[str]) -> dict:
    return {
        "baseline_product_median": ProductMedianBaseline(product_columns),
        "random_forest": RandomForestRegressor(
            n_estimators=300, min_samples_leaf=2, random_state=RANDOM_STATE, n_jobs=-1
        ),
        "hist_gb_monotonic": HistGradientBoostingRegressor(
            learning_rate=0.08,
            max_iter=400,
            monotonic_cst=monotonic_constraints(feature_columns),
            random_state=RANDOM_STATE,
        ),
    }


def cross_validate_temporal(model, X: pd.DataFrame, y: pd.Series, n_splits: int = CV_SPLITS) -> dict:
    """CV com TimeSeriesSplit (folds respeitam a ordem temporal — X já vem ordenado)."""
    maes, wapes = [], []
    for train_idx, val_idx in TimeSeriesSplit(n_splits=n_splits).split(X):
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        pred = model.predict(X.iloc[val_idx])
        maes.append(mean_absolute_error(y.iloc[val_idx], pred))
        wapes.append(wape(y.iloc[val_idx], pred))
    return {
        "cv_mae_mean": round(float(np.mean(maes)), 4),
        "cv_mae_std": round(float(np.std(maes)), 4),
        "cv_wape_mean": round(float(np.mean(wapes)), 4),
    }


def check_elasticity_sanity(model, df: pd.DataFrame, feature_columns: list[str], product_columns: list[str]) -> dict:
    """Verifica, produto a produto, se a curva preço→demanda prevista é não-crescente.

    Curvas crescentes indicam que o modelo aprendeu ruído — com a restrição
    monotônica do campeão isso deve ficar em 100%, e o valor é registrado na
    metadata como evidência.
    """
    tolerance = 1e-6
    well_behaved = []
    for prod_name, prod_df in df.groupby("product_name"):
        base_price = float(prod_df["price"].median())
        competitor = float(prod_df["competitor_price"].mean())
        prices = np.linspace(max(10.0, base_price * 0.5), base_price * 1.5, 30)
        rows = [
            build_feature_row(prod_name, p, competitor, day_of_week=3, is_weekend=0, product_columns=product_columns)
            for p in prices
        ]
        demand = model.predict(pd.DataFrame(rows)[feature_columns])
        increases = np.diff(demand) > tolerance
        well_behaved.append(not increases.any())

    share = float(np.mean(well_behaved)) if well_behaved else 0.0
    return {"products_checked": len(well_behaved), "monotonic_share": round(share, 4)}


def optimize_prices(model, df: pd.DataFrame, feature_columns: list[str], product_columns: list[str]) -> dict:
    """Varre uma grade de preços por produto e escolhe o P* que maximiza receita prevista."""
    optimal_pricing = {}
    for prod_name, prod_df in df.groupby("product_name"):
        avg_competitor = float(prod_df["competitor_price"].mean())
        base_price = float(prod_df["price"].median())

        candidate_prices = np.arange(max(10.0, base_price * 0.5), base_price * 1.5, 5.0)
        rows = [
            build_feature_row(prod_name, p, avg_competitor, day_of_week=3, is_weekend=0, product_columns=product_columns)
            for p in candidate_prices
        ]
        demands = model.predict(pd.DataFrame(rows)[feature_columns])
        revenues = candidate_prices * np.clip(demands, 0, None)

        best_i = int(np.argmax(revenues))
        avg_daily_units = float(prod_df["units_sold"].mean())
        current_revenue = base_price * avg_daily_units
        max_revenue = float(revenues[best_i])
        lift = ((max_revenue - current_revenue) / current_revenue) * 100 if current_revenue > 0 else 0.0

        optimal_pricing[prod_name] = {
            "base_price": round(base_price, 2),
            "optimal_price": round(float(candidate_prices[best_i]), 2),
            "competitor_price": round(avg_competitor, 2),
            "expected_daily_demand": round(float(demands[best_i]), 2),
            "projected_daily_revenue": round(max_revenue, 2),
            "current_daily_revenue": round(current_revenue, 2),
            "revenue_lift_pct": round(lift, 2),
        }
        logger.info(
            f"Otimização {prod_name}: Base R$ {base_price:.2f} -> Ótimo R$ {candidate_prices[best_i]:.2f} | Lift {lift:.2f}%"
        )
    return optimal_pricing


def train_and_select(df: pd.DataFrame, mlflow_enabled: bool = False) -> tuple[object, dict]:
    """Pipeline completo: features → split temporal → CV → seleção → refit → sanity check.

    Retorna (modelo campeão treinado em todos os dados, metadata).
    """
    X, y, feature_columns, product_columns = build_training_frame(df)
    df_sorted = df.sort_values("sale_date").reset_index(drop=True)

    train_idx, test_idx = temporal_split(df_sorted)
    if len(test_idx) < 20 or len(train_idx) < 50:
        raise ValueError(
            f"Dados insuficientes para validação temporal (treino={len(train_idx)}, holdout={len(test_idx)})."
        )
    logger.info(
        f"Split temporal: {len(train_idx)} obs de treino, {len(test_idx)} obs de holdout (últimos {HOLDOUT_DAYS} dias)"
    )

    candidates = build_candidates(feature_columns, product_columns)
    results = {}
    for name, model in candidates.items():
        cv = (
            cross_validate_temporal(model, X.iloc[train_idx], y.iloc[train_idx])
            if name != "baseline_product_median"
            else {}
        )
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        holdout = compute_metrics(y.iloc[test_idx], model.predict(X.iloc[test_idx]))

        elasticity_share = None
        if name != "baseline_product_median":
            elasticity_share = check_elasticity_sanity(model, df_sorted, feature_columns, product_columns)[
                "monotonic_share"
            ]

        results[name] = {**holdout, **cv}
        if elasticity_share is not None:
            results[name]["elasticity_monotonic_share"] = elasticity_share
        logger.info(
            f"Candidato {name}: holdout WAPE={holdout['wape']:.4f} MAE={holdout['mae']:.4f} "
            f"R2={holdout['r2_score']:.4f}"
            + (f" | elasticidade monotônica={elasticity_share:.2f}" if elasticity_share is not None else "")
        )

        if mlflow_enabled:
            try:
                with mlflow.start_run(nested=True, run_name=name):
                    mlflow.log_params({"model": name, "holdout_days": HOLDOUT_DAYS, "cv_splits": CV_SPLITS})
                    mlflow.log_metrics({k: v for k, v in results[name].items() if isinstance(v, int | float)})
            except Exception as e:
                logger.warning(f"Erro ao logar candidato {name} no MLflow: {e}")

    # Seleção em dois estágios: (1) gate de validade econômica — só candidatos com
    # curvas de elasticidade sãs podem otimizar preços; (2) menor WAPE no holdout.
    real_models = {k: v for k, v in results.items() if k != "baseline_product_median"}
    eligible = {k: v for k, v in real_models.items() if v["elasticity_monotonic_share"] >= ELASTICITY_GATE}
    if eligible:
        champion_name = min(eligible, key=lambda k: eligible[k]["wape"])
        rejected = set(real_models) - set(eligible)
        if rejected:
            logger.info(
                f"Candidatos reprovados no gate de elasticidade (< {ELASTICITY_GATE:.0%} monotônico): {sorted(rejected)}"
            )
    else:
        champion_name = min(real_models, key=lambda k: real_models[k]["wape"])
        logger.warning(
            "ATENÇÃO: nenhum candidato passou no gate de elasticidade — usando o de menor WAPE mesmo assim."
        )

    baseline_wape = results["baseline_product_median"]["wape"]
    champion_wape = results[champion_name]["wape"]
    beats_baseline = champion_wape < baseline_wape
    if not beats_baseline:
        logger.warning(
            f"ATENÇÃO: campeão ({champion_name}, WAPE={champion_wape:.4f}) NÃO supera o baseline (WAPE={baseline_wape:.4f})."
        )

    # Refit do campeão com todos os dados (prática padrão após a seleção validada)
    champion = build_candidates(feature_columns, product_columns)[champion_name]
    champion.fit(X, y)

    elasticity = check_elasticity_sanity(champion, df_sorted, feature_columns, product_columns)
    logger.info(
        f"Campeão: {champion_name} | supera baseline: {beats_baseline} | "
        f"curvas monotônicas: {elasticity['monotonic_share'] * 100:.1f}% de {elasticity['products_checked']} produtos"
    )

    dates = pd.to_datetime(df_sorted["sale_date"])
    metadata = {
        # Chaves legadas mantidas para compatibilidade com a API/portal
        "model_metrics": results[champion_name],
        "feature_columns": feature_columns,
        "product_one_hot_columns": product_columns,
        "last_trained": datetime.now().isoformat(),
        # Rigor de validação — evidência de como o modelo foi selecionado
        "champion_model": champion_name,
        "beats_baseline": beats_baseline,
        "selection_criteria": f"gate de elasticidade (monotônica >= {ELASTICITY_GATE:.0%}) + menor WAPE no holdout",
        "baseline_metrics": results["baseline_product_median"],
        "candidate_metrics": results,
        "validation": {
            "scheme": "temporal_holdout + TimeSeriesSplit",
            "holdout_days": HOLDOUT_DAYS,
            "cv_splits": CV_SPLITS,
            "train_rows": int(len(train_idx)),
            "holdout_rows": int(len(test_idx)),
            "training_window": {
                "start": str(dates.min().date()),
                "end": str(dates.max().date()),
            },
        },
        "elasticity_check": elasticity,
    }
    return champion, metadata


def _load_features_from_time_travel(base_dir: str, sales_version: int | None, customers_version: int | None) -> pd.DataFrame:
    """Reconstrói ml_features_pricing a partir de versões históricas do Delta Lake."""
    customers_delta_path = os.path.join(base_dir, "storage", "lakehouse", "crm", "customers")
    sales_delta_path = os.path.join(base_dir, "storage", "lakehouse", "ecommerce", "sales")

    dt_cust = DeltaTable(customers_delta_path, version=customers_version) if customers_version is not None else DeltaTable(customers_delta_path)
    dt_sales = DeltaTable(sales_delta_path, version=sales_version) if sales_version is not None else DeltaTable(sales_delta_path)

    conn = duckdb.connect()
    conn.register("customers_raw", dt_cust.to_pandas())
    conn.register("sales_raw", dt_sales.to_pandas())

    df = conn.execute(
        """
        WITH stg_sales AS (
            SELECT CAST(sale_id AS INT) AS sale_id,
                   TRIM(product) AS product_name,
                   CAST(amount AS DOUBLE) AS amount,
                   CAST(competitor_price AS DOUBLE) AS competitor_price,
                   UPPER(status) AS status,
                   CAST(sale_date AS TIMESTAMP) AS sale_date,
                   ROW_NUMBER() OVER (PARTITION BY sale_id ORDER BY sale_date DESC) AS rn
            FROM sales_raw
        ),
        completed AS (
            SELECT * FROM stg_sales WHERE rn = 1 AND status = 'COMPLETED'
        ),
        daily AS (
            SELECT product_name,
                   CAST(sale_date AS DATE) AS sale_date,
                   amount AS price,
                   AVG(competitor_price) AS competitor_price,
                   COUNT(*) AS units_sold,
                   SUM(amount) AS total_revenue
            FROM completed
            GROUP BY 1, 2, 3
        )
        SELECT product_name, sale_date, price,
               COALESCE(competitor_price, price) AS competitor_price,
               units_sold, total_revenue,
               EXTRACT(dow FROM sale_date) AS day_of_week,
               CASE WHEN EXTRACT(dow FROM sale_date) IN (0, 6) THEN 1 ELSE 0 END AS is_weekend
        FROM daily
        """
    ).fetchdf()
    conn.close()
    return df


def train_model(sales_version: int | None = None, customers_version: int | None = None):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    db_path = os.environ.get("DB_PATH", os.path.join(base_dir, "storage", "analytics.duckdb"))
    model_dir = os.path.join(base_dir, "storage", "model_registry")
    os.makedirs(model_dir, exist_ok=True)

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

    # 1. Extração das features
    if sales_version is not None or customers_version is not None:
        logger.info(f"Modo Time Travel Ativado. Sales Version: {sales_version}, Customers Version: {customers_version}")
        df = _load_features_from_time_travel(base_dir, sales_version, customers_version)
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

    # 2. Treino, validação e seleção
    parent_run = None
    if mlflow_enabled:
        try:
            parent_run = mlflow.start_run(run_name="pricing_training")
            mlflow.log_param("n_rows", len(df))
            if sales_version is not None:
                mlflow.log_param("sales_delta_version", sales_version)
            if customers_version is not None:
                mlflow.log_param("customers_delta_version", customers_version)
        except Exception as e:
            logger.warning(f"Erro ao iniciar MLflow run: {e}")
            mlflow_enabled = False

    champion, metadata = train_and_select(df, mlflow_enabled=mlflow_enabled)

    # 3. Otimização de preços com o campeão
    feature_columns = metadata["feature_columns"]
    product_columns = metadata["product_one_hot_columns"]
    metadata["optimal_prices"] = optimize_prices(champion, df, feature_columns, product_columns)

    # 4. Persistência (registry local + MLflow)
    model_path = os.path.join(model_dir, "pricing_model.joblib")
    joblib.dump(champion, model_path)
    logger.info(f"Modelo campeão ({metadata['champion_model']}) persistido em: {model_path}")

    metadata_path = os.path.join(model_dir, "pricing_metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as mf:
        json.dump(metadata, mf, indent=2)
    logger.info(f"Metadados de precificação persistidos em: {metadata_path}")

    if mlflow_enabled and parent_run is not None:
        try:
            mlflow.log_metrics({k: v for k, v in metadata["model_metrics"].items() if isinstance(v, int | float)})
            mlflow.log_metric("elasticity_monotonic_share", metadata["elasticity_check"]["monotonic_share"])
            mlflow.sklearn.log_model(champion, "model", registered_model_name="pricing_champion")
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
