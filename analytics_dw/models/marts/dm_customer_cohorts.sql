{#
    Matriz de retenção por coorte de aquisição. A coorte de um cliente é o mês da
    sua primeira compra concluída; para cada mês subsequente medimos quantos
    clientes daquela coorte voltaram a comprar (month_offset = distância em meses
    desde a aquisição). Alimenta o heatmap de retenção do dashboard executivo e é
    a base para leitura de churn e lifetime.
#}

WITH completed_sales AS (
    SELECT
        customer_id,
        DATE_TRUNC('month', sale_date) AS activity_month
    FROM {{ ref('fct_sales') }}
    WHERE status = 'COMPLETED'
),

cohort AS (
    SELECT
        customer_id,
        MIN(activity_month) AS cohort_month
    FROM completed_sales
    GROUP BY customer_id
),

activity AS (
    SELECT DISTINCT
        cs.customer_id,
        c.cohort_month,
        cs.activity_month,
        DATEDIFF('month', c.cohort_month, cs.activity_month) AS month_offset
    FROM completed_sales AS cs
    INNER JOIN cohort AS c ON cs.customer_id = c.customer_id
),

cohort_size AS (
    SELECT
        cohort_month,
        COUNT(DISTINCT customer_id) AS cohort_customers
    FROM cohort
    GROUP BY cohort_month
),

retention AS (
    SELECT
        cohort_month,
        month_offset,
        COUNT(DISTINCT customer_id) AS active_customers
    FROM activity
    GROUP BY cohort_month, month_offset
)

SELECT
    r.cohort_month,
    r.month_offset,
    cs.cohort_customers,
    r.active_customers,
    ROUND(100.0 * r.active_customers / NULLIF(cs.cohort_customers, 0), 1) AS retention_pct
FROM retention AS r
INNER JOIN cohort_size AS cs ON r.cohort_month = cs.cohort_month
ORDER BY r.cohort_month, r.month_offset
