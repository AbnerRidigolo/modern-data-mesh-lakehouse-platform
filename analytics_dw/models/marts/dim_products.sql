{{ config(materialized='table') }}

select
    row_number() over (order by product_name) as product_id,
    product_name,
    description,
    category
from {{ ref('products_catalog') }}
