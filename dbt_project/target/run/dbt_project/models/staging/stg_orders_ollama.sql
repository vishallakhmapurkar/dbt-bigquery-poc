
  
    

    create or replace table `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`stg_orders_ollama`
      
    
    

    
    OPTIONS()
    as (
      ```sql
{ config(materialized='view') }

SELECT
  orders_id AS order_id,
  customer_id AS customer_id,
  order_date,
  status
FROM `dbt-hackathon-genai`.dbt_vlakhmapurkar.orders
```
    );
  