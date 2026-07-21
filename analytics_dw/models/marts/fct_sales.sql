{{
    config(
        materialized='incremental',
        unique_key='sale_id',
        incremental_strategy='delete+insert',
    )
}}

WITH sales AS (
    SELECT * FROM {{ ref('stg_sales') }}
    {% if is_incremental() %}
    -- Processa apenas vendas mais recentes que o watermark já materializado,
    -- com 1 dia de lookback para absorver eventos atrasados (late-arriving data)
    WHERE sale_date > (
        SELECT COALESCE(MAX(sale_date), TIMESTAMP '1900-01-01') - INTERVAL 1 DAY
        FROM {{ this }}
    )
    {% endif %}
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
