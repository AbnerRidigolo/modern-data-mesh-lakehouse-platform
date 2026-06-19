WITH completed_sales AS (
    SELECT * 
    FROM {{ ref('fct_sales') }}
    WHERE status = 'COMPLETED'
),

daily_aggregation AS (
    SELECT
        product_name,
        CAST(sale_date AS DATE) AS sale_date,
        amount AS price,
        -- Take the average competitor price for that day/product (in case of slight fluctuations)
        AVG(competitor_price) AS competitor_price,
        COUNT(*) AS units_sold,
        SUM(amount) AS total_revenue
    FROM completed_sales
    GROUP BY 1, 2, 3
)

SELECT
    product_name,
    sale_date,
    price,
    COALESCE(competitor_price, price) AS competitor_price,
    units_sold,
    total_revenue,
    EXTRACT(dow FROM sale_date) AS day_of_week,
    CASE WHEN EXTRACT(dow FROM sale_date) IN (0, 6) THEN 1 ELSE 0 END AS is_weekend
FROM daily_aggregation
