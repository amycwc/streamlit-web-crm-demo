import streamlit as st
import pandas as pd
import logging
from django.db.models import Q

logging.basicConfig(level=logging.INFO)


def search_customers(customer_id="", phone="", filters_dict=None):
    """
    Optimized search that applies all filters at the database level.
   
    Args:
        customer_id: Customer ID to search for
        phone: Phone number to search for
        filters_dict: Dictionary of {field_name: value} for additional filters
   
    Returns:
        QuerySet filtered by all criteria
    """
    from crm_model.models import CustomerProfile
   
    # Start with base queryset - don't fetch all
    query = CustomerProfile.objects.all()
   
    # Apply filters at database level using Q objects for OR logic (fuzzy matching)
    q_objects = Q()
   
    if customer_id:
        q_objects |= Q(customer_id__icontains=customer_id)
   
    if phone:
        q_objects |= Q(phone_number__icontains=phone)
   
    if filters_dict:
        for field_name, field_value in filters_dict.items():
            if field_value:
                q_objects |= Q(**{f"{field_name}__icontains": field_value})
   
    # Apply all Q objects at once
    if q_objects:
        query = query.filter(q_objects)
   
    # Only select necessary fields to reduce data transfer
    return query.values("customer_id", "phone_number", "email", "first_name", "last_name")


# Initialize session state for filters
if 'selected_filter' not in st.session_state:
    st.session_state['selected_filter'] = []

# UI Layout
col1, col2 = st.columns(2)

with col1:
    with st.form("my_form"):
        input_customer_id = st.text_input("Customer ID", "")
        input_phone = st.text_input("Phone", "")
        submit = st.form_submit_button('Search')

    selected_filter = st.multiselect(
        'Filter By',
        ['first_name', 'last_name', 'email'],
        max_selections=3)

with col2:
    # Collect filter values for all selected filters
    filter_values = {}
    if selected_filter:
        for filter_name in selected_filter:
            filter_values[filter_name] = st.text_input(
                f"Enter value for {filter_name}",
                key=f"input_{filter_name}")

if submit:
    # Store in session for reference
    st.session_state['customer_id'] = input_customer_id
    st.session_state['phone'] = input_phone
    st.session_state['selected_filter'] = selected_filter
   
    try:
        # Execute optimized search with all filters applied at DB level
        results = search_customers(
            customer_id=input_customer_id,
            phone=input_phone,
            filters_dict=filter_values
        )
       
        results_list = list(results)
       
        if results_list:
            # Create DataFrame from results
            df_results = pd.DataFrame(results_list)
           
            # Vectorized operation for creating dashboard links
            df_results['dashboard'] = df_results['customer_id'].astype(str).apply(
                lambda x: f"/customer_dashboard?customer_id={x}"
            )
           
            # Reorder columns for better UX
            display_columns = ["customer_id", "first_name", "last_name", "email", "phone_number", "dashboard"]
            df_results = df_results[[col for col in display_columns if col in df_results.columns]]
           
            # Display results
            st.data_editor(
                df_results,
                column_config={
                    "customer_id": "Customer ID",
                    "first_name": "First Name",
                    "last_name": "Last Name",
                    "email": "Email",
                    "phone_number": "Phone Number",
                    "dashboard": st.column_config.LinkColumn(
                        "View",
                        display_text="📊 Dashboard"
                    ),
                },
                hide_index=True,
                use_container_width=True,
            )
            st.success(f"Found {len(results_list)} customer(s)")
        else:
            st.info("No customers found matching the search criteria.")
       
    except Exception as e:
        st.error(f"Search Error: {str(e)}")
        logging.error(f"Search failed: {e}", exc_info=True)
