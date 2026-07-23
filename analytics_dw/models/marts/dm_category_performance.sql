{#
    Performance comercial por categoria de produto. Junta a fato de vendas à
    dimensão de produtos (via product_name) para atribuir cada venda concluída a
    uma categoria e calcular receita, pedidos, unidades e participação (share) no
    faturamento total. Alimenta o drill-down por categoria do dashboard executivo.
#}

WITH completed_sales AS (
    SELECT
        s.sale_id,
        s.customer_id,
        s.product_name,
        s.amount
    FROM {{ ref('fct_sales') }} AS s
    WHERE s.status = 'COMPLETED'
),

with_category AS (
    SELECT
        COALESCE(p.category, 'Sem Categoria') AS category,
        cs.sale_id,
        cs.customer_id,
        cs.amount
    FROM completed_sales AS cs
    LEFT JOIN {{ ref('dim_products') }} AS p
        ON cs.product_name = p.product_name
),

by_category AS (
    SELECT
        category,
        ROUND(SUM(amount), 2) AS net_revenue,
        COUNT(DISTINCT sale_id) AS orders,
        COUNT(DISTINCT customer_id) AS unique_customers
    FROM with_category
    GROUP BY category
)

SELECT
    category,
    net_revenue,
    orders,
    unique_customers,
    CASE
        WHEN orders > 0 THEN ROUND(net_revenue / orders, 2)
        ELSE 0
    END AS average_ticket,
    ROUND(
        100.0 * net_revenue / NULLIF(SUM(net_revenue) OVER (), 0), 2
    ) AS revenue_share_pct
FROM by_category
ORDER BY net_revenue DESC
