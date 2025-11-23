

  create or replace view `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`stg_products`
  OPTIONS()
  as 

SELECT
    product_id, product_name, category, price
FROM `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`products`;

