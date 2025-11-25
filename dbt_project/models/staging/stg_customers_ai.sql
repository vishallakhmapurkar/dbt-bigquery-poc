{{ config(materialized='view') }}

SELECT
    customer_id AS customers_id,
    customer_id AS customer_id,
    first_name,
    last_name
FROM {{ source('dbt_vlakhmapurkar', 'customers') }}