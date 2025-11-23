
    
    

with child as (
    select customer_id as from_field
    from `dbt2025`.`dbt_vlakhmapurkar`.`orders`
    where customer_id is not null
),

parent as (
    select  as to_field
    from 
)

select
    from_field

from child
left join parent
    on child.from_field = parent.to_field

where parent.to_field is null


