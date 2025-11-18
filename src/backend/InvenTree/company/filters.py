"""Custom query filters for the Company app."""

from decimal import Decimal

from django.db.models import DecimalField, Value


def annotate_on_order_quantity():
    """Annotate the 'on_order' quantity for each SupplierPart in a queryset.

    Note: Purchase order functionality has been removed from this system.
    This function now returns 0 for all supplier parts.
    """
    # Purchase orders have been removed - return 0
    return Value(0, output_field=DecimalField())
