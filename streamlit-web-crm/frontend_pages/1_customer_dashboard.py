import streamlit as st
import pandas as pd
import logging
from crm_model.models import CustomerProfile, CustomerManager,CustomerSegment
from crm_model.views import get_customer_metrics,get_customer_txn

# For Streamlit < 1.30
customer_id = st.query_params.get('customer_id', [''])[0] if not st.query_params.get('customer_id', [''])[0] else st.query_params.get('customer_id', [''])

with st.form("my_form"):
     input_customer_id = st.text_input("Customer ID", "" if not customer_id else customer_id)
     submit = st.form_submit_button('Search')


if submit or customer_id:
    st.session_state['Customer_ID'] = input_customer_id
    try:
        customer_query = CustomerProfile.objects.all()
        if st.session_state.get('Customer_ID'):
            exact_query = customer_query.filter(customer_id=st.session_state['Customer_ID'])
        exact_profile = list(exact_query.values(
                "customer_id",
                "first_name",
                "last_name",
                "gender",
                "date_of_birth",
                "is_active",
            ))
        exact_contact = list(exact_query.values(
                "phone_number",
                "email",
                "address",
                "city",
                "state",
            ))
        metrics = get_customer_metrics(st.session_state['Customer_ID'])
        top_txn = get_customer_txn(st.session_state['Customer_ID'])
        
        # Compute and display an icon + segment label above demographics
        gender = None
        if exact_profile and len(exact_profile):
            gender = exact_profile[0].get('gender')

        g = (str(gender).strip().lower() if gender is not None else '')
        if 'f' in g or 'female' in g:
            gender_icon = '👩'
        elif 'm' in g or 'male' in g:
            gender_icon = '👨'
        elif g:
            gender_icon = '🧑'
        else:
            gender_icon = '👤'

        cid = st.session_state.get('Customer_ID')
        seg_obj = None
        segment = None
        if cid:
            try:
                # Convert to int if string
                cid_int = int(cid)
                seg_obj = CustomerSegment.objects.filter(customer__customer_id=cid_int).first()
                
                if not seg_obj:
                    # Calculate segment if not exists
                    try:
                        seg_obj = CustomerSegment.calculate_for_customer(cid_int)
                    except Exception as calc_error:
                        st.warning(f"Could not calculate segment: {calc_error}")
                        seg_obj = None
            except ValueError:
                st.error(f"Invalid customer ID: {cid}")
            except Exception as e:
                st.error(f"Error loading segment: {e}")
                seg_obj = None
        
        if seg_obj:
            segment = seg_obj.segment

        # Build customer name
        customer_name = f"{exact_profile[0].get('first_name', '')} {exact_profile[0].get('last_name', '')}".strip()
        
        # Segment display with styling
        segment_icon_map = {
            'Champion': '⭐',
            'Loyal': '💎',
            'At Risk': '⚠️',
            'Hibernating': '💤',
        }
        segment_color_map = {
            'Champion': '#FFD700',
            'Loyal': "#41C1E1", 
            'At Risk': '#FF6347',
            'Hibernating': '#A9A9A9',
        }
        
        segment_display = segment or 'New customer'
        segment_icon = segment_icon_map.get(segment, '🆕')
        segment_color = segment_color_map.get(segment, '#808080')
        
        # Calculate RFM score for stars (1-5 scale)
        rfm_score = 3  # default
        if seg_obj:
            rfm_score = min(5, max(1, (seg_obj.r_score + seg_obj.f_score + seg_obj.m_score) // 3))
        
        stars = '★' * rfm_score + '☆' * (5 - rfm_score)
        
        # Determine buyer level based on total spent
        total_spent = metrics.get('total_spent', 0)
        if total_spent >= 1000:
            buyer_badge = 'Platinum buyer'
        elif total_spent >= 500:
            buyer_badge = 'Gold buyer'
        elif total_spent >= 200:
            buyer_badge = 'Silver buyer'
        else:
            buyer_badge = 'Bronze buyer'
        
        # Profile header card
        with st.container():
            st.markdown(f"""
            <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                        padding: 30px; border-radius: 15px; margin-bottom: 20px;'>
                <div style='display: flex; align-items: center; gap: 20px;'>
                    <div style='background: white; width: 120px; height: 120px; border-radius: 50%; 
                                display: flex; align-items: center; justify-content: center; font-size: 60px;'>
                        {gender_icon}
                    </div>
                    <div style='flex: 1; color: white;'>
                        <h1 style='margin: 0; color: white;'>{customer_name}</h1>
                        <p style='margin: 3px 0;'> Customer ID: {metrics.get('customer_id', '—')}</p>
                        <p style='margin: 5px 0; font-size: 18px; color: {segment_color}; font-weight: bold;'>
                            {segment_icon} {segment_display}
                        </p>
                        <p style='margin: 5px 0; font-size: 24px;'>{stars}</p>
                        <p style='margin: 5px 0; background: rgba(255,255,255,0.2); 
                                  padding: 5px 10px; border-radius: 20px; display: inline-block;'>
                            {buyer_badge}
                        </p>
                        <div style='margin-top: 10px; font-size: 14px;'>
                            <p style='margin: 3px 0;'>📅 Customer since {metrics.get('member_since', '—')}</p>
                            <p style='margin: 3px 0;'>🛒 Last purchase: {metrics.get('last_purchase', '—')}</p>
                            <p style='margin: 3px 0;'>📱 {exact_contact[0].get('phone_number', '—')} | 
                               ✉️ {exact_contact[0].get('email', '—')}</p>
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # Spending metrics
        col_spent, col_predicted = st.columns(2)
        with col_spent:
            st.metric(
                label="💰 Spent so far",
                value=f"${total_spent:,.0f}",
                delta=f"{metrics.get('txn_count', 0)} orders"
            )
        with col_predicted:
            # Simple prediction: average * expected remaining orders
            predicted = total_spent * 1.1  # (POC only) 10% growth prediction
            st.metric(
                label="📈 Predicted to spend",
                value=f"${predicted:,.0f}",
                delta=f"+${predicted - total_spent:,.0f}"
            )
        
        st.markdown("---")
        
        # Detailed info tabs
        tab1, tab2, tab3 = st.tabs(["📊 Details", "📦 Recent Orders", "⭐ Top Products"])
        
        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### Demographics")
                demo_data = {
                    'Gender': exact_profile[0].get('gender', '—'),
                    'Date of Birth': exact_profile[0].get('date_of_birth', '—'),
                    'Active Status': '✅ Active' if exact_profile[0].get('is_active') else '❌ Inactive'
                }
                for k, v in demo_data.items():
                    st.text(f"{k}: {v}")
            
            with col2:
                st.markdown("#### Location")
                location_data = {
                    'Address': exact_contact[0].get('address', '—'),
                    'City': exact_contact[0].get('city', '—'),
                    'State': exact_contact[0].get('state', '—')
                }
                for k, v in location_data.items():
                    st.text(f"{k}: {v}")
        
        with tab2:
            st.dataframe(
                pd.DataFrame(top_txn.get('recent_txns', [])),
                hide_index=True,
                use_container_width=True
            )
        
        with tab3:
            st.dataframe(
                pd.DataFrame(top_txn.get('top_products', []), columns=['Product', 'Quantity']),
                hide_index=True,
                use_container_width=True
            )

    except Exception as e:
        st.error(f"Error: {e}")
        logging.error(f"Failed to connect to the database: {e}")
