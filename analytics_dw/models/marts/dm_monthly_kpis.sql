WITH fct_sales AS (
    SELECT * FROM {{ ref('fct_sales') }}
),

monthly_metrics AS (
    SELECT
        DATE_TRUNC('month', sale_date) AS sales_month,
        COUNT(DISTINCT sale_id) AS total_orders,
        
        -- COMPLETED metrics
        SUM(CASE WHEN status = 'COMPLETED' THEN amount ELSE 0 END) AS net_revenue,
        COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) AS completed_orders_count,
        
        -- CANCELLED metrics
        COUNT(CASE WHEN status = 'CANCELLED' THEN 1 END) AS cancelled_orders_count,
        
        -- Quality tracking metrics
        SUM(is_orphan_join) AS orphan_joins_count
    FROM fct_sales
    GROUP BY 1
)

SELECT
    sales_month,
    total_orders,
    net_revenue,
    completed_orders_count,
    cancelled_orders_count,
    orphan_joins_count,
    -- Calculate Average Ticket (avoid division by zero)
    CASE 
        WHEN completed_orders_count > 0 THEN ROUND(net_revenue / completed_orders_count, 2)
        ELSE 0 
    END AS average_ticket
FROM monthly_metrics
ORDER BY sales_month DESC
