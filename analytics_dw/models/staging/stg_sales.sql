WITH source AS (
    SELECT * FROM delta_scan('{{ env_var("STORAGE_PATH", "/opt/airflow/storage") }}/lakehouse/ecommerce/sales')
),

renamed AS (
    SELECT
        CAST(sale_id AS INT) AS sale_id,
        CAST(customer_id AS INT) AS customer_id,
        TRIM(product) AS product_name,
        CAST(amount AS DOUBLE) AS amount,
        CAST(competitor_price AS DOUBLE) AS competitor_price,
        UPPER(status) AS status,
        CAST(sale_date AS TIMESTAMP) AS sale_date
    FROM source
)

SELECT * FROM renamed
