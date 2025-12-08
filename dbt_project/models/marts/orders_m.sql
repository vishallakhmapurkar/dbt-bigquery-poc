{{ config(materialized='table') }}

SELECT
    *
FROM {{ ref('v_orders') }}