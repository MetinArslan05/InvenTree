"""Custom query filters for the Part app.

The code here makes heavy use of subquery annotations!

Useful References:

- https://hansonkd.medium.com/the-dramatic-benefits-of-django-subqueries-and-annotations-4195e0dafb16
- https://pypi.org/project/django-sql-utils/
- https://docs.djangoproject.com/en/4.0/ref/models/expressions/
- https://stackoverflow.com/questions/42543978/django-1-11-annotating-a-subquery-aggregate

"""

from decimal import Decimal
from typing import Optional

from django.db import models
from django.db.models import (
    Case,
    DecimalField,
    Exists,
    ExpressionWrapper,
    F,
    FloatField,
    Func,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Cast, Coalesce, Greatest
from django.db.models.query import QuerySet

from sql_util.utils import SubquerySum

import InvenTree.conversion
import InvenTree.helpers
import part.models
import stock.models


def annotate_in_production_quantity(reference: str = '') -> QuerySet:
    """Annotate the 'in production' quantity for each part in a queryset.

    Note: Build order functionality has been removed from this system.
    This function now returns 0 for all parts.

    Arguments:
        reference: Reference to the part from the current queryset (default = '')
    """
    # Build orders have been removed - return 0
    return Value(0, output_field=DecimalField())


def annotate_scheduled_to_build_quantity(reference: str = '') -> QuerySet:
    """Annotate the 'scheduled to build' quantity for each part in a queryset.

    Note: Build order functionality has been removed from this system.
    This function now returns 0 for all parts.
    """
    # Build orders have been removed - return 0
    return Value(0, output_field=IntegerField())


def annotate_on_order_quantity(reference: str = '') -> QuerySet:
    """Annotate the 'on order' quantity for each part in a queryset.

    Note: Purchase order functionality has been removed from this system.
    This function now returns 0 for all parts.
    """
    # Purchase orders have been removed - return 0
    return Value(0, output_field=DecimalField())


def annotate_total_stock(reference: str = '', filter: Optional[Q] = None) -> QuerySet:
    """Annotate 'total stock' quantity against a queryset.

    - This function calculates the 'total stock' for a given part
    - Finds all stock items associated with each part (using the provided filter)
    - Aggregates the 'quantity' of each relevant stock item

    Args:
        reference (str): The relationship reference of the part from the current model e.g. 'part'
        filter (Q): Q object which defines how to filter the stock items
    """
    # Stock filter only returns 'in stock' items
    stock_filter = stock.models.StockItem.IN_STOCK_FILTER

    if filter is not None:
        stock_filter &= filter

    return Coalesce(
        SubquerySum(f'{reference}stock_items__quantity', filter=stock_filter),
        Decimal(0),
        output_field=models.DecimalField(),
    )


def annotate_build_order_requirements(reference: str = '') -> QuerySet:
    """Annotate the total quantity of each part required for build orders.

    Note: Build order functionality has been removed from this system.
    This function now returns 0 for all parts.
    """
    # Build orders have been removed - return 0
    return Value(0, output_field=models.DecimalField())


def annotate_build_order_allocations(reference: str = '', location=None) -> QuerySet:
    """Annotate the total quantity of each part allocated to build orders.

    Note: Build order functionality has been removed from this system.
    This function now returns 0 for all parts.

    Arguments:
        reference: The relationship reference of the part from the current model
        location: If provided, only allocated stock items from this location are considered (ignored)
    """
    # Build orders have been removed - return 0
    return Value(0, output_field=models.DecimalField())


def annotate_sales_order_requirements(reference: str = '') -> QuerySet:
    """Annotate the total quantity of each part required for sales orders.

    Note: Sales order functionality has been removed from this system.
    This function now returns 0 for all parts.
    """
    # Sales orders have been removed - return 0
    return Value(0, output_field=models.DecimalField())


def annotate_sales_order_allocations(reference: str = '', location=None) -> QuerySet:
    """Annotate the total quantity of each part allocated to sales orders.

    Note: Sales order functionality has been removed from this system.
    This function now returns 0 for all parts.

    Arguments:
        reference: The relationship reference of the part from the current model
        location: If provided, only allocated stock items from this location are considered (ignored)
    """
    # Sales orders have been removed - return 0
    return Value(0, output_field=models.DecimalField())


def variant_stock_query(reference: str = '', filter: Optional[Q] = None) -> QuerySet:
    """Create a queryset to retrieve all stock items for variant parts under the specified part.

    - Useful for annotating a queryset with aggregated information about variant parts

    Args:
        reference: The relationship reference of the part from the current model
        filter: Q object which defines how to filter the returned StockItem instances
    """
    stock_filter = stock.models.StockItem.IN_STOCK_FILTER

    if filter:
        stock_filter &= filter

    return stock.models.StockItem.objects.filter(
        part__tree_id=OuterRef(f'{reference}tree_id'),
        part__lft__gt=OuterRef(f'{reference}lft'),
        part__rght__lt=OuterRef(f'{reference}rght'),
    ).filter(stock_filter)


def annotate_variant_quantity(subquery: Q, reference: str = 'quantity') -> QuerySet:
    """Create a subquery annotation for all variant part stock items on the given parent query.

    Args:
        subquery: A 'variant_stock_query' Q object
        reference: The relationship reference of the variant stock items from the current queryset
    """
    return Coalesce(
        Subquery(
            subquery.annotate(
                total=Func(F(reference), function='SUM', output_field=FloatField())
            )
            .values('total')
            .order_by()
        ),
        0,
        output_field=FloatField(),
    )


def annotate_category_parts() -> QuerySet:
    """Construct a queryset annotation which returns the number of parts in a particular category.

    - Includes parts in subcategories also
    - Requires subquery to perform annotation
    """
    # Construct a subquery to provide all parts in this category and any subcategories:
    subquery = part.models.Part.objects.exclude(category=None).filter(
        category__tree_id=OuterRef('tree_id'),
        category__lft__gte=OuterRef('lft'),
        category__rght__lte=OuterRef('rght'),
        category__level__gte=OuterRef('level'),
    )

    return Coalesce(
        Subquery(
            subquery.annotate(
                total=Func(F('pk'), function='COUNT', output_field=IntegerField())
            )
            .values('total')
            .order_by()
        ),
        0,
        output_field=IntegerField(),
    )


def annotate_default_location(reference: str = '') -> QuerySet:
    """Construct a queryset that finds the closest default location in the part's category tree.

    If the part's category has its own default_location, this is returned.
    If not, the category tree is traversed until a value is found.
    """
    subquery = part.models.PartCategory.objects.filter(
        tree_id=OuterRef(f'{reference}tree_id'),
        lft__lt=OuterRef(f'{reference}lft'),
        rght__gt=OuterRef(f'{reference}rght'),
        level__lte=OuterRef(f'{reference}level'),
        parent__isnull=False,
        default_location__isnull=False,
    ).order_by('-level')

    return Coalesce(
        F(f'{reference}default_location'),
        Subquery(subquery.values('default_location')[:1]),
        Value(None),
        output_field=IntegerField(),
    )


def annotate_sub_categories() -> QuerySet:
    """Construct a queryset annotation which returns the number of subcategories for each provided category."""
    subquery = part.models.PartCategory.objects.filter(
        tree_id=OuterRef('tree_id'),
        lft__gt=OuterRef('lft'),
        rght__lt=OuterRef('rght'),
        level__gt=OuterRef('level'),
    )

    return Coalesce(
        Subquery(
            subquery.annotate(
                total=Func(F('pk'), function='COUNT', output_field=IntegerField())
            )
            .values('total')
            .order_by()
        ),
        0,
        output_field=IntegerField(),
    )


def annotate_bom_item_can_build(queryset: QuerySet, reference: str = '') -> QuerySet:
    """Annotate the 'can_build' quantity for each BomItem in a queryset.

    Arguments:
        queryset: A queryset of BomItem objects
        reference: Reference to the BomItem from the current queryset (default = '')

    To do this we need to also annotate some other fields which are used in the calculation:

    - total_in_stock: Total stock quantity for the part (may include variant stock)
    - available_stock: Total available stock quantity for the part
    - variant_stock: Total stock quantity for any variant parts
    - substitute_stock: Total stock quantity for any substitute parts

    And then finally, annotate the 'can_build' quantity for each BomItem:
    """
    # Pre-fetch the required related fields
    queryset = queryset.prefetch_related(
        f'{reference}sub_part',
        f'{reference}sub_part__stock_items',
        f'{reference}sub_part__stock_items__allocations',
        f'{reference}sub_part__stock_items__sales_order_allocations',
        f'{reference}substitutes',
        f'{reference}substitutes__part__stock_items',
    )

    # Queryset reference to the linked sub_part instance
    sub_part_ref = f'{reference}sub_part__'

    # Apply some aliased annotations to the queryset
    queryset = queryset.annotate(
        # Total stock quantity (just for the sub_part itself)
        total_stock=annotate_total_stock(sub_part_ref),
        # Total allocated to sales orders
        allocated_to_sales_orders=annotate_sales_order_allocations(sub_part_ref),
        # Total allocated to build orders
        allocated_to_build_orders=annotate_build_order_allocations(sub_part_ref),
    )

    # Annotate the "available" stock, based on the total stock and allocations
    queryset = queryset.annotate(
        available_stock=Greatest(
            ExpressionWrapper(
                F('total_stock')
                - F('allocated_to_sales_orders')
                - F('allocated_to_build_orders'),
                output_field=models.DecimalField(),
            ),
            Decimal(0),
            output_field=models.DecimalField(),
        )
    )

    # Annotate the total stock for any variant parts
    vq = variant_stock_query(reference=sub_part_ref)

    queryset = queryset.alias(
        variant_stock_total=annotate_variant_quantity(vq, reference='quantity'),
        variant_bo_allocations=annotate_variant_quantity(
            vq, reference='sales_order_allocations__quantity'
        ),
        variant_so_allocations=annotate_variant_quantity(
            vq, reference='allocations__quantity'
        ),
    )

    # Annotate total variant stock
    queryset = queryset.annotate(
        available_variant_stock=Greatest(
            ExpressionWrapper(
                F('variant_stock_total')
                - F('variant_bo_allocations')
                - F('variant_so_allocations'),
                output_field=FloatField(),
            ),
            0,
            output_field=FloatField(),
        )
    )

    # Account for substitute parts
    substitute_ref = f'{reference}substitutes__part__'

    # Extract similar information for any 'substitute' parts
    queryset = queryset.alias(
        substitute_stock=annotate_total_stock(reference=substitute_ref),
        substitute_build_allocations=annotate_build_order_allocations(
            reference=substitute_ref
        ),
        substitute_sales_allocations=annotate_sales_order_allocations(
            reference=substitute_ref
        ),
    )

    # Calculate 'available_substitute_stock' field
    queryset = queryset.annotate(
        available_substitute_stock=Greatest(
            ExpressionWrapper(
                F('substitute_stock')
                - F('substitute_build_allocations')
                - F('substitute_sales_allocations'),
                output_field=models.DecimalField(),
            ),
            Decimal(0),
            output_field=models.DecimalField(),
        )
    )

    # Now we can annotate the total "available" stock for the BomItem
    queryset = queryset.alias(
        total_stock=ExpressionWrapper(
            F('available_variant_stock')
            + F('available_substitute_stock')
            + F('available_stock'),
            output_field=FloatField(),
        )
    )

    # And finally, we can annotate the 'can_build' quantity for each BomItem
    queryset = queryset.annotate(
        can_build=Greatest(
            ExpressionWrapper(
                Case(
                    When(Q(quantity=0), then=Value(0)),
                    default=(F('total_stock') - F('setup_quantity'))
                    / (F('quantity') * (1.0 + F('attrition') / 100.0)),
                    output_field=FloatField(),
                ),
                output_field=FloatField(),
            ),
            Decimal(0),
            output_field=FloatField(),
        )
    )

    return queryset


"""A list of valid operators for filtering part parameters."""
PARAMETER_FILTER_OPERATORS: list[str] = ['gt', 'gte', 'lt', 'lte', 'ne', 'icontains']


def filter_by_parameter(
    queryset: QuerySet, template_id: int, value: str, func: str = ''
) -> QuerySet:
    """Filter the given queryset by a given template parameter.

    Parts which do not have a value for the given parameter are excluded.

    Arguments:
        queryset: A queryset of Part objects
        template_id (int): The ID of the template parameter to filter by
        value (str): The value of the parameter to filter by
        func (str): The function to use for the filter (e.g. __gt, __lt, __contains)

    Returns:
        A queryset of Part objects filtered by the given parameter
    """
    if func and func not in PARAMETER_FILTER_OPERATORS:
        raise ValueError(f'Invalid parameter filter function supplied: {func}.')

    try:
        template = part.models.PartParameterTemplate.objects.get(pk=template_id)
    except (ValueError, part.models.PartParameterTemplate.DoesNotExist):
        # Return queryset unchanged if the template does not exist
        return queryset

    # Construct a "numeric" value
    try:
        value_numeric = float(value)
    except (ValueError, TypeError):
        value_numeric = None

    if template.checkbox:
        # Account for 'boolean' parameter values
        # Convert to "True" or "False" string in this case
        bool_value = InvenTree.helpers.str2bool(value)
        value_numeric = 1 if bool_value else 0
        value = str(bool_value)

        # Boolean filtering is limited to exact matches
        func = ''

    elif value_numeric is None and template.units:
        # Convert the raw value to the units of the template parameter
        try:
            value_numeric = InvenTree.conversion.convert_physical_value(
                value, template.units
            )
        except Exception:
            # The value cannot be converted - return an empty queryset
            return queryset.none()

    # Special handling for the "not equal" operator
    if func == 'ne':
        invert = True
        func = ''
    else:
        invert = False

    # Some filters are only applicable to string values
    text_only = any([func in ['icontains'], value_numeric is None])

    # Ensure the function starts with a double underscore
    if func and not func.startswith('__'):
        func = f'__{func}'

    # Query for 'numeric' value - this has priority over 'string' value
    data_numeric = {
        'parameters__template': template,
        'parameters__data_numeric__isnull': False,
        f'parameters__data_numeric{func}': value_numeric,
    }

    query_numeric = Q(**data_numeric)

    # Query for 'string' value
    data_text = {
        'parameters__template': template,
        f'parameters__data{func}': str(value),
    }

    if not text_only:
        data_text['parameters__data_numeric__isnull'] = True

    query_text = Q(**data_text)

    # Combine the queries based on whether we are filtering by text or numeric value
    q = query_text if text_only else query_text | query_numeric

    # Special handling for the '__ne' (not equal) operator
    # In this case, we want the *opposite* of the above queries
    if invert:
        return queryset.exclude(q).distinct()
    else:
        return queryset.filter(q).distinct()


def order_by_parameter(
    queryset: QuerySet, template_id: int, ascending: bool = True
) -> QuerySet:
    """Order the given queryset by a given template parameter.

    Parts which do not have a value for the given parameter are ordered last.

    Arguments:
        queryset: A queryset of Part objects
        template_id (int): The ID of the template parameter to order by
        ascending (bool): Order by ascending or descending (default = True)

    Returns:
        A queryset of Part objects ordered by the given parameter
    """
    template_filter = part.models.PartParameter.objects.filter(
        template__id=template_id, part_id=OuterRef('id')
    )

    # Annotate the queryset with the parameter value, and whether it exists
    queryset = queryset.annotate(parameter_exists=Exists(template_filter))

    # Annotate the text data value
    queryset = queryset.annotate(
        parameter_value=Case(
            When(
                parameter_exists=True,
                then=Subquery(
                    template_filter.values('data')[:1], output_field=models.CharField()
                ),
            ),
            default=Value('', output_field=models.CharField()),
        ),
        parameter_value_numeric=Case(
            When(
                parameter_exists=True,
                then=Subquery(
                    template_filter.values('data_numeric')[:1],
                    output_field=models.FloatField(),
                ),
            ),
            default=Value(0, output_field=models.FloatField()),
        ),
    )

    prefix = '' if ascending else '-'

    # Return filtered queryset

    return queryset.order_by(
        '-parameter_exists',
        f'{prefix}parameter_value_numeric',
        f'{prefix}parameter_value',
    )
