WITH sales AS (
    SELECT * FROM {{ ref('stg_sales') }}
),

deduped_sales AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY sale_id ORDER BY sale_date DESC) as rn
    FROM sales
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
    s.competitor_price,
    s.status,
    s.sale_date,
    -- Business metadata flags
    CASE WHEN c.customer_id IS NULL THEN 1 ELSE 0 END AS is_orphan_join
FROM deduped_sales s
LEFT JOIN customers c ON s.customer_id = c.customer_id
WHERE s.rn = 1
