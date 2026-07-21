"""Engenharia de features do modelo de precificação — fonte única de verdade.

Treino, otimização de preço e servimento (endpoint /ml/simulate) constroem as
features por AQUI, eliminando training-serving skew: qualquer feature nova é
adicionada uma vez e flui automaticamente para os três caminhos.

Todas as features são computáveis no momento da inferência a partir do contexto
(produto, preço candidato, preço do concorrente, dia da semana) — sem lags que
exigiriam estado histórico no servidor.
"""
import math

import pandas as pd

# Features numéricas na ordem canônica (a ordem importa para as restrições
# monotônicas do HistGradientBoosting — ver train.py)
NUMERIC_FEATURES = [
    "price",
    "competitor_price",
    "price_ratio",       # preço próprio / concorrente: captura posicionamento competitivo
    "log_price",         # elasticidade tende a ser mais linear em log-preço
    "day_of_week",
    "is_weekend",
    "dow_sin",           # codificação cíclica: dom(0) e sáb(6) ficam próximos
    "dow_cos",
]

PRODUCT_PREFIX = "prod_"


def _base_row(price: float, competitor_price: float, day_of_week: int, is_weekend: int) -> dict:
    competitor = competitor_price if competitor_price and competitor_price > 0 else price
    return {
        "price": float(price),
        "competitor_price": float(competitor),
        "price_ratio": float(price) / float(competitor),
        "log_price": math.log(max(float(price), 1e-6)),
        "day_of_week": int(day_of_week),
        "is_weekend": int(is_weekend),
        "dow_sin": math.sin(2 * math.pi * int(day_of_week) / 7.0),
        "dow_cos": math.cos(2 * math.pi * int(day_of_week) / 7.0),
    }


def build_feature_row(
    product_name: str,
    price: float,
    competitor_price: float,
    day_of_week: int,
    is_weekend: int,
    product_columns: list[str],
) -> dict:
    """Monta uma única linha de features para inferência (simulador/otimizador)."""
    row = _base_row(price, competitor_price, day_of_week, is_weekend)
    for col in product_columns:
        row[col] = 1 if col == f"{PRODUCT_PREFIX}{product_name}" else 0
    return row


def build_training_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, list[str], list[str]]:
    """Transforma o dataframe bruto (ml_features_pricing) em X, y.

    Retorna (X, y, feature_columns, product_columns) com X ordenado por
    sale_date — pré-requisito para o split temporal e o TimeSeriesSplit.
    """
    df = df.sort_values("sale_date").reset_index(drop=True)

    engineered = pd.DataFrame(
        [
            _base_row(r.price, r.competitor_price, int(r.day_of_week), int(r.is_weekend))
            for r in df.itertuples()
        ]
    )

    dummies = pd.get_dummies(df["product_name"], prefix=PRODUCT_PREFIX.rstrip("_"), dtype=int)
    product_columns = sorted(dummies.columns.tolist())

    X = pd.concat([engineered, dummies[product_columns]], axis=1)
    feature_columns = NUMERIC_FEATURES + product_columns
    X = X[feature_columns]
    y = df["units_sold"].astype(float)

    return X, y, feature_columns, product_columns


def monotonic_constraints(feature_columns: list[str]) -> list[int]:
    """Restrições de monotonicidade (conhecimento de domínio): demanda não pode
    AUMENTAR quando o nosso preço sobe — em nível, em razão ou em log.
    0 = sem restrição; -1 = monotônica decrescente; +1 = crescente."""
    decreasing = {"price", "price_ratio", "log_price"}
    return [-1 if col in decreasing else 0 for col in feature_columns]
