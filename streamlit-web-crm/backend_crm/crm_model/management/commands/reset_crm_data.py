from django.core.management.base import BaseCommand
from crm_model.models import CustomerProfile, Product, PurchaseHistory

class Command(BaseCommand):
    help = "Delete ALL CRM data (customers, products, purchases). Use with caution."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", action="store_true", help="Actually perform the deletion.")

    def handle(self, *args, **options):
        if not options["confirm"]:
            self.stdout.write(self.style.WARNING("No action taken. Re-run with --confirm to delete all data."))
            return
        deleted_purchases = PurchaseHistory.objects.all().delete()
        deleted_products = Product.objects.all().delete()
        deleted_customers = CustomerProfile.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(
            f"Deleted: customers={deleted_customers[0]}, products={deleted_products[0]}, purchases={deleted_purchases[0]}"
        ))
