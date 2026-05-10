from datetime import timedelta
from django.db import models
from django.utils import timezone
from django.db.models import Sum, F, ExpressionWrapper, FloatField

class CustomerManager(models.Manager):
    def search_by_id_and_phone(self, customer_id, phone_number):
        qs = self.get_queryset()
        if customer_id:
            qs = qs.filter(customer_id__icontains=customer_id)
        if phone_number:
            qs = qs.filter(phone_number__icontains=phone_number)
        return qs

    def update_customer_profile(self, customer_id, phone_number, **kwargs):
        allowed_fields = {
            'phone_number',
            'email'
        }

        update_data = {key: value for key, value in kwargs.items() if key in allowed_fields}

        return self.get_queryset().filter(
            customer_id=customer_id,
            phone_number=phone_number
            ).update(**update_data)
    
class CustomerProfile(models.Model):
    # Django adds an implicit AutoField primary key named `id`; we keep a custom one for clarity.
    customer_id = models.AutoField(primary_key=True)
    first_name = models.CharField(max_length=255, db_index=True)
    last_name = models.CharField(max_length=255, db_index=True)
    gender = models.CharField(max_length=50, db_index=True)
    date_of_birth = models.DateTimeField(db_index=True)
    email = models.EmailField(max_length=255, unique=True, db_index=True)
    phone_number = models.CharField(max_length=20, unique=True, db_index=True)
    signup_date = models.DateTimeField()
    address = models.TextField()
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=50, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    objects = CustomerManager()

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"


class Product(models.Model):
    product_id = models.AutoField(primary_key=True)
    product_name = models.CharField(max_length=255, db_index=True)
    category = models.CharField(max_length=100, db_index=True)
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)
    brand = models.CharField(max_length=100, db_index=True)
    product_description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.product_name} ({self.brand})"


class PurchaseHistory(models.Model):
    purchase_id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="purchases")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="purchases")
    purchase_date = models.DateTimeField()
    quantity = models.PositiveIntegerField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)


class CustomerSegment(models.Model):
    """Stores RFM/RRFM-style segment and scores for a customer.

    This model includes simple helper methods to calculate R (recency in days),
    F (frequency), M (monetary) and simple bucketed scores. The scoring rules
    are intentionally simple and can be adjusted to your business needs.
    """
    customer = models.OneToOneField(CustomerProfile, on_delete=models.CASCADE, related_name='segment')
    recency_days = models.IntegerField(null=True, blank=True)
    frequency = models.IntegerField(null=True, blank=True)
    monetary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    r_score = models.IntegerField(null=True, blank=True)
    f_score = models.IntegerField(null=True, blank=True)
    m_score = models.IntegerField(null=True, blank=True)
    rfm_score = models.IntegerField(null=True, blank=True)
    segment = models.CharField(max_length=64, null=True, blank=True)
    last_calculated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Customer Segment'
        verbose_name_plural = 'Customer Segments'

    def __str__(self):
        return f"{self.customer} -> {self.segment or 'unsegmented'}"

    @classmethod
    def _score_recency(cls, days: int) -> int:
        if days is None:
            return 1
        if days <= 30:
            return 5
        if days <= 90:
            return 4
        if days <= 180:
            return 3
        if days <= 365:
            return 2
        return 1

    @classmethod
    def _score_frequency(cls, freq: int) -> int:
        if not freq:
            return 1
        if freq >= 20:
            return 5
        if freq >= 10:
            return 4
        if freq >= 5:
            return 3
        if freq >= 2:
            return 2
        return 1

    @classmethod
    def _score_monetary(cls, monetary: float) -> int:
        if not monetary:
            return 1
        if monetary >= 1000:
            return 5
        if monetary >= 500:
            return 4
        if monetary >= 200:
            return 3
        if monetary >= 50:
            return 2
        return 1

    @classmethod
    def calculate_for_customer(cls, customer_id):
        """Calculate and store RFM-style metrics for a single customer.

        Returns the `CustomerSegment` instance.
        """
        customer = CustomerProfile.objects.filter(customer_id=customer_id).first()
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        # compute aggregates using ORM
        txns = PurchaseHistory.objects.filter(customer=customer).select_related('product')
        line_total_expr = ExpressionWrapper(F('product__price_per_unit') * F('quantity'), output_field=FloatField())

        aggs = txns.aggregate(
            total_spent=Sum(line_total_expr),
            total_qty=Sum('quantity'),
            last_purchase=Sum(0)  # placeholder to ensure structure; we'll compute differently below
        )

        # Determine last purchase separately
        last_purchase = txns.aggregate(last= models.Max('purchase_date')).get('last')

        # raw values
        total_spent = float(aggs.get('total_spent') or 0.0)
        total_qty = int(aggs.get('total_qty') or 0)
        frequency = txns.values('purchase_date').distinct().count()  # Count the purchase count as frequency

        recency_days = None
        if last_purchase: #data up to 2023
            recency_days = (timezone.now() + timedelta(days=-730) - last_purchase).days

        # compute scores
        r_score = cls._score_recency(recency_days)
        f_score = cls._score_frequency(frequency)
        m_score = cls._score_monetary(total_spent)
        rfm_score = r_score * 100 + f_score * 10 + m_score

        # simple segmentation rules (customize to your business)
        if r_score >= 4 and f_score >= 4 and m_score >= 4:
            segment = 'Champion'
        elif f_score >= 4:
            segment = 'Loyal'
        elif r_score <= 2 and f_score <= 2:
            segment = 'At Risk'
        else:
            segment = 'Hibernating'

        obj, _ = cls.objects.update_or_create(
            customer=customer,
            defaults={
                'recency_days': recency_days,
                'frequency': frequency,
                'monetary': total_spent,
                'r_score': r_score,
                'f_score': f_score,
                'm_score': m_score,
                'rfm_score': rfm_score,
                'segment': segment,
            }
        )
        return obj

    @classmethod
    def calculate_for_all(cls):
        """Calculate segments for all customers. This loops customers and calls
        `calculate_for_customer`. For large datasets, replace with batch/SQL logic.
        """
        for cust in CustomerProfile.objects.all().values_list('customer_id', flat=True):
            try:
                cls.calculate_for_customer(cust)
            except Exception:
                # ignore single failures but continue
                continue
    
