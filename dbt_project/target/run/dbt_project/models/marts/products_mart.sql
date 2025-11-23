

  create or replace view `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`products_mart`
  OPTIONS()
  as 

SELECT
    product_id, product_name, category, price
FROM `dbt-hackathon-genai`.`dbt_vlakhmapurkar`.`products`;

