{#
    Série temporal diária de receita (vendas concluídas) com média móvel de 7
    dias e variação dia-a-dia. Alimenta o gráfico de tendência do dashboard
    executivo e a detecção visual de sazonalidade.
#}

WITH daily AS (
    SELECT
        CAST(sale_date AS DATE) AS revenue_date,
        SUM(CASE WHEN status = 'COMPLETED' THEN amount ELSE 0 END) AS net_revenue,
        COUNT(DISTINCT CASE WHEN status = 'COMPLETED' THEN sale_id END) AS orders,
        COUNT(DISTINCT CASE WHEN status = 'COMPLETED' THEN customer_id END) AS active_customers
    FROM {{ ref('fct_sales') }}
    GROUP BY 1
)

SELECT
    revenue_date,
    ROUND(net_revenue, 2) AS net_revenue,
    orders,
    active_customers,
    ROUND(AVG(net_revenue) OVER (
        ORDER BY revenue_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ), 2) AS revenue_7d_avg,
    ROUND(net_revenue - LAG(net_revenue) OVER (ORDER BY revenue_date), 2) AS revenue_dod_delta
FROM daily
ORDER BY revenue_date
