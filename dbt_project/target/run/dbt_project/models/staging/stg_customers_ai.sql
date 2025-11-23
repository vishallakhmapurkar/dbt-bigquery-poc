

  create or replace view `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`stg_customers_ai`
  OPTIONS()
  as 

SELECT
    id AS customers_id,
    user_id AS customer_id,
    first_name,
    last_name
FROM `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`customers`;

