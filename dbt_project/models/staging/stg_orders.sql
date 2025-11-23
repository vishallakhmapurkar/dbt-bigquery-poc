{{ config(materialized='view') }}
select
    order_id,
    customer_id,
    order_date,
    status
from {{ source('dbt_vlakhmapurkar', 'orders') }}