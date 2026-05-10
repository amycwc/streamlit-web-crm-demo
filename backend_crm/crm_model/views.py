from django.shortcuts import render
from django.http import JsonResponse
from functools import lru_cache
from django.db.models import Sum, Max, F, ExpressionWrapper, FloatField, DateField
from crm_model.models import CustomerProfile, PurchaseHistory


def customer_list(request=None):
    """Return a list of customer dicts.

    - If called as a Django view (request provided) -> returns JsonResponse.
    - If called directly (e.g. from Streamlit with no request) -> returns Python list[dict]
    """
    # Use Django ORM to fetch customer records
    customers = CustomerProfile.objects.all()

    # Build a list of dictionaries. Fill missing/optional fields with None so
    # frontends like Streamlit can render a consistent table.
    customers_data = []
    for c in customers:
        customers_data.append({
            "customer_id": getattr(c, 'customer_id', None),
            "first_name": getattr(c, 'first_name', None),
            "last_name": getattr(c, 'last_name', None),
            "email": getattr(c, 'email', None),
            "gender": getattr(c, 'gender', None),
            "date_of_birth": getattr(c, 'date_of_birth', None),
            "phone_number": getattr(c, 'phone_number', None),
            "signup_date": getattr(c, 'signup_date', None),
            "address": getattr(c, 'address', None),
            "city": getattr(c, 'city', None),
            "state": getattr(c, 'state', None),
            "zip_code": getattr(c, 'zip_code', None),
            "is_active": getattr(c, 'is_active', None)
        })

    if request is not None:
        return JsonResponse({"customers": customers_data})

    return customers_data



@lru_cache(maxsize=256)
def get_customer_metrics(customer_id: int) -> dict:
    customer = CustomerProfile.objects.filter(customer_id=customer_id).first()
    if not customer:
        return {"error": "not_found"}

    # Annotate each transaction with a computed line_total = product.price_per_unit * quantity
    txns = PurchaseHistory.objects.filter(customer=customer).select_related('product')

    # Some databases require numeric casting; ExpressionWrapper ensures correct type
    line_total_expr = ExpressionWrapper(
        F('product__price_per_unit') * F('quantity'), output_field=FloatField()
    )

    aggregates = txns.aggregate(
        total_spent=Sum(line_total_expr),
        total_qty=Sum('quantity'),
        txn_count=Sum(ExpressionWrapper(F('quantity') * 0 + 1, output_field=FloatField())),
        last_purchase=Max('purchase_date'),
    )
    member_since = customer.signup_date
    total_spent = float(aggregates.get('total_spent') or 0.0)
    total_qty = int(aggregates.get('total_qty') or 0)
    txn_count = int(aggregates.get('txn_count') or 0)
    last_purchase = aggregates.get('last_purchase')

    avg_order_value = (total_spent / txn_count) if txn_count else 0.0

    # Normalize dates to YYYY-MM-DD for easier display
    def _date_only(dt):
        if not dt:
            return None
        try:
            return dt.date().isoformat()
        except Exception:
            return str(dt)

    return {
        'customer_id': customer.customer_id,
        'member_since': _date_only(member_since),
        'last_purchase': _date_only(last_purchase),
        'total_spent': total_spent,
        'txn_count': txn_count,
        'total_qty': total_qty,
        'avg_order_value': avg_order_value,
    }

@lru_cache(maxsize=256)
def get_customer_txn(customer_id: int) -> dict:
    customer = CustomerProfile.objects.filter(customer_id=customer_id).first()
    if not customer:
        return {"error": "not_found"}

    # Annotate each transaction with a computed line_total = product.price_per_unit * quantity
    txns = PurchaseHistory.objects.filter(customer=customer).select_related('product')

    # Some databases require numeric casting; ExpressionWrapper ensures correct type
    line_total_expr = ExpressionWrapper(
        F('product__price_per_unit') * F('quantity'), output_field=FloatField()
    )

    # Compute top products by quantity using values + annotate + order_by
    top_products_qs = (
        txns.values('product__product_name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:5]
    )
    top_products = [(p['product__product_name'] or 'Unknown', int(p['total_qty'] or 0)) for p in top_products_qs]

    recent_txns = (
        txns.annotate(line_total=line_total_expr)
        .order_by('-purchase_date')[:5]
        .values('purchase_id', 'purchase_date', 'product__product_name', 'quantity', 'line_total')
    )

    # Convert recent_txns queryset of dicts into plain list with friendly keys
    recent_txn_list = []
    for r in recent_txns:
        recent_txn_list.append({
            'purchase_id': r.get('purchase_id'),
            'date': r.get('purchase_date'),
            'product': r.get('product__product_name'),
            'quantity': r.get('quantity'),
            'line_total': float(r.get('line_total') or 0),
        })

    # Normalize dates to YYYY-MM-DD for easier display
    def _date_only(dt):
        if not dt:
            return None
        try:
            return dt.date().isoformat()
        except Exception:
            return str(dt)

    return {
        'customer_id': customer.customer_id,
        'top_products': top_products,
        'recent_txns': recent_txn_list,
    }