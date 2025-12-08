{{ config(materialized='view') }}

SELECT
    customer_id AS customer_id,
    first_name AS first_name,
    last_name AS last_name
FROM
    {{ source('dbt_vlakhmapurkar', 'customers') }}