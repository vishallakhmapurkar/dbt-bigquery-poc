
  
    

    create or replace table `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`stg_customers_ollama`
      
    
    

    
    OPTIONS()
    as (
      ```sql
{ config(materialized='view') }

SELECT
  renamed_col('customers', 'customer_id', 'id') AS customers_id,
  first_name,
  last_name
FROM
  `dbt-hackathon-genai.dbt_vlakhmapurkar.customers`
```
    );
  