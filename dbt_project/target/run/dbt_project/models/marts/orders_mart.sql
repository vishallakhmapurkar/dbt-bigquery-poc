
  
    

    create or replace table `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`orders_mart`
      
    
    

    
    OPTIONS()
    as (
      

SELECT
    *
FROM `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`stg_orders`
    );
  