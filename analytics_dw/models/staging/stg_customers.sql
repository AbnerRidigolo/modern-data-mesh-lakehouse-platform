WITH source AS (
    SELECT * FROM delta_scan('{{ env_var("STORAGE_PATH", "/opt/airflow/storage") }}/lakehouse/crm/customers')
),

renamed AS (
    SELECT
        CAST(id AS INT) AS customer_id,
        TRIM(name) AS customer_name,
        LOWER(email) AS email,
        CAST(created_at AS TIMESTAMP) AS created_at,
        LOWER(status) AS status
    FROM source
)

SELECT * FROM renamed
