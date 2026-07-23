{#
    Feature view (offline store): features de produto no grão produto-dia.

    Cada linha representa "o que se sabia sobre o produto ao FIM do dia
    feature_date" — janelas móveis de 7/30 dias calculadas com window frames
    RANGE (robustas a dias sem venda). O feature store faz o point-in-time
    join estrito (evento em D usa features de D-1 ou antes) para treino, e a
    materialização envia a última linha de cada produto ao online store.
#}

WITH product_daily AS (
    SELECT
        product_name,
        CAST(sale_date AS DATE) AS feature_date,
        SUM(units_sold) AS units_day,
        SUM(total_revenue) AS revenue_day,
        AVG(price) AS avg_price_day,
        AVG(competitor_price) AS avg_competitor_price_day
    FROM {{ ref('ml_features_pricing') }}
    GROUP BY 1, 2
)

SELECT
    product_name,
    feature_date,
    SUM(units_day) OVER w7 AS units_7d,
    ROUND(SUM(revenue_day) OVER w7, 2) AS revenue_7d,
    SUM(units_day) OVER w30 AS units_30d,
    ROUND(SUM(revenue_day) OVER w30, 2) AS revenue_30d,
    ROUND(AVG(avg_price_day) OVER w30, 2) AS avg_price_30d,
    ROUND(COALESCE(STDDEV(avg_price_day) OVER w30, 0), 2) AS price_volatility_30d,
    ROUND(AVG(avg_price_day / NULLIF(avg_competitor_price_day, 0)) OVER w30, 4) AS price_ratio_30d
FROM product_daily
WINDOW
    w7 AS (
        PARTITION BY product_name
        ORDER BY feature_date
        RANGE BETWEEN INTERVAL 6 DAY PRECEDING AND CURRENT ROW
    ),
    w30 AS (
        PARTITION BY product_name
        ORDER BY feature_date
        RANGE BETWEEN INTERVAL 29 DAY PRECEDING AND CURRENT ROW
    )
