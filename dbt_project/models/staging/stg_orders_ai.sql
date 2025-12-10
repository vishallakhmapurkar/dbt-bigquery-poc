{{ config(materialized='view') }}

SELECT
    order_id AS orders_id,
    customer_id AS customer_id,
    order_date AS order_date,
    status AS status
FROM
    {{ source('dbt_vlakhmapurkar', 'orders') }}