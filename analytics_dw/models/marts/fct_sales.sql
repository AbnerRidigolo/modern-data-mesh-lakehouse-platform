WITH sales AS (
    SELECT * FROM {{ ref('stg_sales') }}
),

customers AS (
    SELECT * FROM {{ ref('dim_customers') }}
)

SELECT
    s.sale_id,
    s.customer_id,
    COALESCE(c.customer_name, 'Desconhecido (Órfão)') AS customer_name,
    s.product_name,
    s.amount,
    s.status,
    s.sale_date,
    -- Business metadata flags
    CASE WHEN c.customer_id IS NULL THEN 1 ELSE 0 END AS is_orphan_join
FROM sales s
LEFT JOIN customers c ON s.customer_id = c.customer_id
