{{ config(materialized='view') }}

SELECT
    order_id AS orders_id,
    customer_id,
    order_date,
    status
FROM {{ source('dbt_vlakhmapurkar', 'orders') }}