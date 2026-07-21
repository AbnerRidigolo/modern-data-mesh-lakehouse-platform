"""Testes do pipeline de treinamento de precificação: split temporal, baseline,
consistência treino-serving e restrição de monotonicidade do campeão."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from domains.ml_pricing.features import (
    NUMERIC_FEATURES,
    build_feature_row,
    build_training_frame,
    monotonic_constraints,
)
from domains.ml_pricing.train import (
    ProductMedianBaseline,
    check_elasticity_sanity,
    temporal_split,
    train_and_select,
    wape,
)


def _synthetic_demand_df(days: int = 90, seed: int = 7) -> pd.DataFrame:
    """Série sintética com elasticidade real: demanda cai com o preço."""
    rng = np.random.default_rng(seed)
    products = {"Produto A": 100.0, "Produto B": 300.0}
    rows = []
    dates = pd.date_range("2026-01-01", periods=days, freq="D")
    for date in dates:
        for prod, base in products.items():
            price = base * rng.uniform(0.8, 1.2)
            competitor = base * rng.uniform(0.9, 1.1)
            demand = max(1.0, 50 - 0.3 * (price - base) + rng.normal(0, 2))
            rows.append(
                {
                    "product_name": prod,
                    "sale_date": date,
                    "price": round(price, 2),
                    "competitor_price": round(competitor, 2),
                    "units_sold": round(demand),
                    "total_revenue": round(price * demand, 2),
                    "day_of_week": date.dayofweek,
                    "is_weekend": 1 if date.dayofweek >= 5 else 0,
                }
            )
    return pd.DataFrame(rows)


class TestFeatureConsistency:
    def test_training_frame_and_serving_row_share_columns(self):
        df = _synthetic_demand_df(days=30)
        X, y, feature_columns, product_columns = build_training_frame(df)

        row = build_feature_row("Produto A", 100.0, 95.0, 3, 0, product_columns)
        # Toda coluna de treino precisa existir na linha de inferência (mesma fonte)
        assert set(feature_columns).issubset(row.keys())
        assert list(X.columns) == feature_columns
        assert len(X) == len(y)

    def test_price_ratio_and_cyclical_encoding(self):
        row = build_feature_row("Produto A", 110.0, 100.0, 6, 1, ["prod_Produto A"])
        assert row["price_ratio"] == pytest.approx(1.1)
        assert row["dow_sin"] == pytest.approx(np.sin(2 * np.pi * 6 / 7))
        assert row["prod_Produto A"] == 1

    def test_zero_competitor_price_falls_back_to_own_price(self):
        row = build_feature_row("Produto A", 100.0, 0.0, 3, 0, [])
        assert row["price_ratio"] == pytest.approx(1.0)

    def test_monotonic_constraints_target_price_features(self):
        cols = NUMERIC_FEATURES + ["prod_X"]
        cst = monotonic_constraints(cols)
        assert cst[cols.index("price")] == -1
        assert cst[cols.index("price_ratio")] == -1
        assert cst[cols.index("log_price")] == -1
        assert cst[cols.index("day_of_week")] == 0
        assert cst[cols.index("prod_X")] == 0


class TestTemporalValidation:
    def test_holdout_is_strictly_after_train(self):
        df = _synthetic_demand_df(days=60).sort_values("sale_date").reset_index(drop=True)
        train_idx, test_idx = temporal_split(df, holdout_days=14)
        assert len(train_idx) > 0 and len(test_idx) > 0
        assert pd.to_datetime(df.loc[train_idx, "sale_date"]).max() < pd.to_datetime(df.loc[test_idx, "sale_date"]).min()

    def test_wape_metric(self):
        assert wape(np.array([10, 10]), np.array([9, 11])) == pytest.approx(0.1)
        assert wape(np.array([0, 0]), np.array([0, 0])) == 0.0


class TestBaseline:
    def test_predicts_per_product_median(self):
        df = _synthetic_demand_df(days=30)
        X, y, _, product_columns = build_training_frame(df)
        baseline = ProductMedianBaseline(product_columns).fit(X, y)
        preds = baseline.predict(X)
        mask_a = X["prod_Produto A"] == 1
        assert np.unique(preds[mask_a.to_numpy()]).size == 1


class TestTrainAndSelect:
    def test_full_pipeline_selects_champion_with_sane_elasticity(self):
        df = _synthetic_demand_df(days=90)
        champion, metadata = train_and_select(df)

        # O campeão deve superar o baseline em dados com sinal real de elasticidade
        assert metadata["beats_baseline"] is True
        assert metadata["champion_model"] in ("random_forest", "hist_gb_monotonic")
        assert metadata["model_metrics"]["wape"] < metadata["baseline_metrics"]["wape"]

        # Gate de validade econômica: o campeão precisa ter curvas de elasticidade sãs
        assert metadata["candidate_metrics"][metadata["champion_model"]]["elasticity_monotonic_share"] >= 0.8

        # Contrato de validação registrado na metadata
        assert metadata["validation"]["scheme"] == "temporal_holdout + TimeSeriesSplit"
        assert metadata["validation"]["holdout_rows"] > 0
        assert "cv_mae_mean" in metadata["candidate_metrics"][metadata["champion_model"]]

        # Sanity check de elasticidade coberto para todos os produtos
        assert metadata["elasticity_check"]["products_checked"] == 2

    def test_monotonic_candidate_produces_nonincreasing_demand_curves(self):
        df = _synthetic_demand_df(days=90)
        from domains.ml_pricing.features import build_training_frame as btf
        from domains.ml_pricing.train import build_candidates

        X, y, feature_columns, product_columns = btf(df)
        model = build_candidates(feature_columns, product_columns)["hist_gb_monotonic"]
        model.fit(X, y)

        result = check_elasticity_sanity(model, df, feature_columns, product_columns)
        assert result["monotonic_share"] == 1.0

    def test_raises_on_insufficient_data(self):
        df = _synthetic_demand_df(days=10)
        with pytest.raises(ValueError, match="insuficientes"):
            train_and_select(df)
