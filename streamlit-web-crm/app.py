# load_data.py
import csv
import os
import sys
import django


# Add the Django project directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend_crm'))

# Configure Django ONCE at the very top of app.py
if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_crm.settings')
    
# Setup Django ONCE - use try/except to prevent re-setup
try:
    django.setup()
except RuntimeError:
    pass  # Already configured

import streamlit as st

# set_page_config must be called before other Streamlit commands
st.set_page_config(page_title='CRM', layout='wide')

st.title('CRM Web Demo')
home_page = st.Page('frontend_pages/0_search_page.py', title='Customer Search')
dashboard = st.Page('frontend_pages/1_customer_dashboard.py', title='Customer Dashboard')
sales_summary = st.Page('frontend_pages/2_sales_summary.py', title='Sales Summary')
ai_assistant = st.Page('frontend_pages/3_ai_assistant.py', title='AI Assistant')
pg = st.navigation([home_page, dashboard, sales_summary, ai_assistant])

pg.run()

