{{ config(materialized='table') }}

SELECT
    *
FROM {{ ref('test_customers') }}