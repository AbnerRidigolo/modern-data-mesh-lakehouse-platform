{% snapshot customers_snapshot %}
{#
    SCD Type 2: historiza mudanças cadastrais dos clientes (nome, e-mail, status).
    Cada alteração detectada fecha a linha vigente (dbt_valid_to) e abre uma nova,
    permitindo reconstruir o estado do cadastro em qualquer ponto do tempo.
#}
{{
    config(
        target_schema='snapshots',
        unique_key='customer_id',
        strategy='check',
        check_cols=['customer_name', 'email', 'status'],
    )
}}

SELECT
    customer_id,
    customer_name,
    email,
    created_at,
    status
FROM {{ ref('stg_customers') }}
QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at DESC) = 1

{% endsnapshot %}
