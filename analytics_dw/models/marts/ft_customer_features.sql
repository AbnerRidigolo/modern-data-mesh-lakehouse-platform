{#
    Feature view (offline store): snapshot atual de features de cliente.

    Grão cliente (uma linha por customer_id), com feature_timestamp marcando
    a última atividade — o online store serve este snapshot com TTL, e a
    freshness é monitorada pela API do feature store.
#}

WITH completed_sales AS (
    SELECT *
    FROM {{ ref('fct_sales') }}
    WHERE status = 'COMPLETED'
      AND is_orphan_join = 0
),

reference_date AS (
    SELECT MAX(CAST(sale_date AS DATE)) AS max_date FROM completed_sales
),

per_customer AS (
    SELECT
        s.customer_id,
        MAX(s.sale_date) AS feature_timestamp,
        COUNT(*) AS total_orders,
        ROUND(SUM(s.amount), 2) AS lifetime_value,
        COUNT(*) FILTER (WHERE CAST(s.sale_date AS DATE) >= r.max_date - INTERVAL 90 DAY) AS orders_90d,
        ROUND(COALESCE(SUM(s.amount) FILTER (WHERE CAST(s.sale_date AS DATE) >= r.max_date - INTERVAL 90 DAY), 0), 2) AS revenue_90d,
        ROUND(COALESCE(AVG(s.amount) FILTER (WHERE CAST(s.sale_date AS DATE) >= r.max_date - INTERVAL 90 DAY), 0), 2) AS avg_ticket_90d,
        DATE_DIFF('day', CAST(MAX(s.sale_date) AS DATE), r.max_date) AS recency_days
    FROM completed_sales s
    CROSS JOIN reference_date r
    GROUP BY s.customer_id, r.max_date
)

SELECT
    c.customer_id,
    c.feature_timestamp,
    c.total_orders,
    c.lifetime_value,
    c.orders_90d,
    c.revenue_90d,
    c.avg_ticket_90d,
    c.recency_days,
    l.rfm_segment
FROM per_customer c
LEFT JOIN {{ ref('dm_customer_ltv') }} l ON c.customer_id = l.customer_id
