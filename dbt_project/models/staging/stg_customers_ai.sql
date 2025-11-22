{{ config(materialized='view') }}

SELECT
    id AS customers_id,
    user_id AS customer_id,
    first_name,
    last_name
FROM {{ source('dbt_vlakhmapurkar', 'customers') }}