
  
    

    create or replace table `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`customers_mart`
      
    
    

    
    OPTIONS()
    as (
      

SELECT
    *
FROM `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`stg_customers`
    );
  