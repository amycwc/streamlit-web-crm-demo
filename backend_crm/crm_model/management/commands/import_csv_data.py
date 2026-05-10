import csv
import pandas as pd
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from crm_model.models import CustomerProfile, Product, PurchaseHistory

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

class Command(BaseCommand):
    help = "Import initial CRM data from CSV files in kaggle_dataset folder into Django ORM (SQLite)."

    def add_arguments(self, parser):
        parser.add_argument("--base-path", type=str, default="kaggle_dataset", help="Path to folder containing CSV files.")
        parser.add_argument("--skip-purchases", action="store_true", help="Skip importing purchase history (faster).")
        parser.add_argument("--overwrite", action="store_true", help="Overwrite existing rows (delete then import).")

    def handle(self, *args, **options):
        base_path = Path(options["base_path"]).resolve()
        if not base_path.exists():
            raise CommandError(f"Base path does not exist: {base_path}")

        customers_csv = base_path / "customer_profile_dataset.csv"
        products_csv = base_path / "products_dataset.csv"
        purchases_csv = base_path / "purchase_history_dataset.csv"

        for p in [customers_csv, products_csv] + ([] if options["skip_purchases"] else [purchases_csv]):
            if not p.exists():
                raise CommandError(f"Required CSV file missing: {p}")

        if options["overwrite"]:
            self.stdout.write(self.style.WARNING("--overwrite specified: deleting existing data."))
            CustomerProfile.objects.all().delete()
            Product.objects.all().delete()
            PurchaseHistory.objects.all().delete()

        with transaction.atomic():
            self.import_customers(customers_csv)
            self.import_products(products_csv)
            if not options["skip_purchases"]:
                self.import_purchases(purchases_csv)

        self.stdout.write(self.style.SUCCESS("Data import completed."))

    def import_customers(self, path: Path):
        df = pd.read_csv(path)
        # Normalize whitespace
        for col in ["first_name","last_name","gender","email","phone_number","address","city","state","zip_code"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        df["customer_id"] = df["customer_id"].astype(int)
        # Exclude existing ids
        existing_ids = set(CustomerProfile.objects.filter(customer_id__in=df["customer_id"].tolist()).values_list("customer_id", flat=True))
        new_rows = df[~df["customer_id"].isin(existing_ids)]
        objs = []
        for _, row in new_rows.iterrows():
            objs.append(CustomerProfile(
                customer_id=int(row.customer_id),
                first_name=row.first_name,
                last_name=row.last_name,
                gender=row.gender,
                date_of_birth=self.parse_dt(row.date_of_birth),
                email=row.email,
                phone_number=row.phone_number,
                signup_date=self.parse_dt(row.signup_date),
                address=row.address,
                city=row.city,
                state=row.get("state") if hasattr(row, "state") else None,
                zip_code=row.get("zip_code") if hasattr(row, "zip_code") else None,
            ))
        CustomerProfile.objects.bulk_create(objs, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"Customers: created {len(objs)}, skipped {len(existing_ids)}"))

    def import_products(self, path: Path):
        df = pd.read_csv(path)
        for col in ["product_name","category","brand","product_description"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        df["product_id"] = df["product_id"].astype(int)
        existing_ids = set(Product.objects.filter(product_id__in=df["product_id"].tolist()).values_list("product_id", flat=True))
        new_rows = df[~df["product_id"].isin(existing_ids)]
        objs = []
        for _, row in new_rows.iterrows():
            price = Decimal(str(row.price_per_unit))
            objs.append(Product(
                product_id=int(row.product_id),
                product_name=row.product_name,
                category=row.category,
                price_per_unit=price,
                brand=row.brand,
                product_description=row.product_description if row.product_description else None,
            ))
        Product.objects.bulk_create(objs, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"Products: created {len(objs)}, skipped {len(existing_ids)}"))

    def import_purchases(self, path: Path):
        df = pd.read_csv(path)
        df["purchase_id"] = df["purchase_id"].astype(int)
        df["customer_id"] = df["customer_id"].astype(int)
        df["product_id"] = df["product_id"].astype(int)
        existing_ids = set(PurchaseHistory.objects.filter(purchase_id__in=df["purchase_id"].tolist()).values_list("purchase_id", flat=True))
        new_rows = df[~df["purchase_id"].isin(existing_ids)]
        # Preload FK maps to avoid per-row queries
        customers_map = {c.customer_id: c for c in CustomerProfile.objects.filter(customer_id__in=new_rows["customer_id"].unique().tolist())}
        products_map = {p.product_id: p for p in Product.objects.filter(product_id__in=new_rows["product_id"].unique().tolist())}
        objs = []
        missing_refs = 0
        for _, row in new_rows.iterrows():
            cust = customers_map.get(int(row.customer_id))
            prod = products_map.get(int(row.product_id))
            if not cust or not prod:
                missing_refs += 1
                continue
            objs.append(PurchaseHistory(
                purchase_id=int(row.purchase_id),
                customer=cust,
                product=prod,
                purchase_date=self.parse_dt(row.purchase_date),
                quantity=int(row.quantity),
                total_amount=Decimal(str(row.total_amount)),
            ))
        PurchaseHistory.objects.bulk_create(objs, ignore_conflicts=True)
        skipped = len(existing_ids)
        self.stdout.write(self.style.SUCCESS(f"Purchases: created {len(objs)}, skipped {skipped}, missing FK {missing_refs}"))

    def parse_dt(self, value: str):
        try:
            return datetime.strptime(value.strip(), DATE_FORMAT)
        except ValueError:
            raise CommandError(f"Invalid datetime format: {value}")
