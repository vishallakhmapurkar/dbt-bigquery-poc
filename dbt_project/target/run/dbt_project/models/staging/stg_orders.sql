

  create or replace view `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`stg_orders`
  OPTIONS()
  as 

SELECT
    order_id AS order_id,
    customer_id AS customer_id,
    order_date AS order_date,
    status AS status
FROM `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`orders`;

