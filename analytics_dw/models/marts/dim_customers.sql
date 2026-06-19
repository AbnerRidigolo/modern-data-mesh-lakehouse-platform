WITH customers AS (
    SELECT * FROM {{ ref('stg_customers') }}
),

deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at DESC) as rn
    FROM customers
)

SELECT
    customer_id,
    customer_name,
    email,
    created_at,
    status,
    -- Add helper flag for active users
    CASE WHEN status = 'active' THEN 1 ELSE 0 END AS is_active_flag
FROM deduped
WHERE rn = 1
