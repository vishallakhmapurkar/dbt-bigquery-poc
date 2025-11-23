
    
    

with dbt_test__target as (

  select email as unique_field
  from `dbt2025`.`dbt_vlakhmapurkar`.`customers`
  where email is not null

)

select
    unique_field,
    count(*) as n_records

from dbt_test__target
group by unique_field
having count(*) > 1


