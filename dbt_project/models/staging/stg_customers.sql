{{ config(materialized='view') }}
select
    customer_id,
    first_name,
    last_name
from {{ source('dbt_vlakhmapurkar', 'customers') }}