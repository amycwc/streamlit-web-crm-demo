#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
"""
# 1. Create and apply migrations for updated Django models
python manage.py makemigrations crm_model
python manage.py migrate

# 2. Import data (basic full import)
python backend_crm/manage.py import_csv_data --base-path kaggle_dataset

# (Optional) Skip huge purchase history for a quick test
python backend_crm/manage.py import_csv_data --base-path kaggle_dataset --skip-purchases

# (Optional) Re-import after wiping existing rows
python backend_crm/manage.py import_csv_data --base-path kaggle_dataset --overwrite

# (Optional) Clear all CRM data safely
python backend_crm/manage.py reset_crm_data --confirm

"""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_crm.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
