WITH customers AS (
    SELECT * FROM {{ ref('stg_customers') }}
)

SELECT
    customer_id,
    customer_name,
    email,
    created_at,
    status,
    -- Add helper flag for active users
    CASE WHEN status = 'active' THEN 1 ELSE 0 END AS is_active_flag
FROM customers
