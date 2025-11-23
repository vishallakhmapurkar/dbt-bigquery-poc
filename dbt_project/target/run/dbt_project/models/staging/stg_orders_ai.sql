

  create or replace view `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`stg_orders_ai`
  OPTIONS()
  as 

SELECT
    order_id AS orders_id,
    customer_id,
    order_date,
    status
FROM `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`orders`;

