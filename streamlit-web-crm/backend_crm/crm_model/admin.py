from django.contrib import admin
from crm_model.models import CustomerSegment
import streamlit as st

# Register your models here.

# if st.button("🔄 Refresh All Customer Segments"):
#     with st.spinner("Calculating segments..."):
#         try:
#             CustomerSegment.calculate_for_all()
#             st.success("✅ All customer segments refreshed!")
#         except Exception as e:
#             st.error(f"Error: {e}")
