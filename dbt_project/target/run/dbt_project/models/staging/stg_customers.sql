

  create or replace view `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`stg_customers`
  OPTIONS()
  as 

SELECT
    customer_id AS customer_id,
    first_name AS first_name,
    last_name AS last_name
FROM `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`customers`;

