{#
    Mart de valor do cliente: métricas de LTV e segmentação RFM
    (Recency / Frequency / Monetary) calculadas sobre vendas concluídas.
#}

WITH completed_sales AS (
    SELECT *
    FROM {{ ref('fct_sales') }}
    WHERE status = 'COMPLETED'
      AND is_orphan_join = 0
),

per_customer AS (
    SELECT
        customer_id,
        customer_name,
        COUNT(*) AS total_orders,
        SUM(amount) AS lifetime_value,
        AVG(amount) AS avg_ticket,
        MIN(sale_date) AS first_purchase_at,
        MAX(sale_date) AS last_purchase_at,
        DATE_DIFF('day', CAST(MAX(sale_date) AS DATE), CURRENT_DATE) AS recency_days
    FROM completed_sales
    GROUP BY 1, 2
),

scored AS (
    SELECT
        *,
        -- Quintis RFM: 5 = melhor (compra recente, frequente, alto valor)
        NTILE(5) OVER (ORDER BY recency_days DESC) AS recency_score,
        NTILE(5) OVER (ORDER BY total_orders ASC) AS frequency_score,
        NTILE(5) OVER (ORDER BY lifetime_value ASC) AS monetary_score
    FROM per_customer
)

SELECT
    customer_id,
    customer_name,
    total_orders,
    ROUND(lifetime_value, 2) AS lifetime_value,
    ROUND(avg_ticket, 2) AS avg_ticket,
    first_purchase_at,
    last_purchase_at,
    recency_days,
    recency_score,
    frequency_score,
    monetary_score,
    CASE
        WHEN recency_score >= 4 AND frequency_score >= 4 AND monetary_score >= 4 THEN 'Champion'
        WHEN recency_score >= 3 AND frequency_score >= 3 THEN 'Loyal'
        WHEN recency_score >= 4 AND frequency_score <= 2 THEN 'New / Promising'
        WHEN recency_score <= 2 AND frequency_score >= 3 THEN 'At Risk'
        WHEN recency_score <= 2 AND frequency_score <= 2 THEN 'Hibernating'
        ELSE 'Regular'
    END AS rfm_segment
FROM scored
