import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from django.db.models import Sum, Count, F, ExpressionWrapper, FloatField, Q
from django.db.models.functions import TruncDate, TruncMonth
from crm_model.models import CustomerProfile, PurchaseHistory, Product, CustomerSegment
import plotly.express as px
import plotly.graph_objects as go


st.title("📊 Sales Summary Dashboard")

# Date range selector
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start Date", datetime(2016, 1, 1).date())
with col2:
    end_date = st.date_input("End Date", datetime(2023, 12, 31).date())

try:
    # Compute line total expression
    line_total_expr = ExpressionWrapper(
        F('product__price_per_unit') * F('quantity'), output_field=FloatField()
    )
    
    # Filter transactions by date range
    txns = PurchaseHistory.objects.filter(
        purchase_date__date__gte=start_date,
        purchase_date__date__lte=end_date
    ).select_related('product', 'customer')
    
    # Overall KPIs
    overall_stats = txns.aggregate(
        total_revenue=Sum(line_total_expr),
        total_orders=Count('purchase_id', distinct=True),
        total_quantity=Sum('quantity'),
        unique_customers=Count('customer', distinct=True)
    )
    
    total_revenue = float(overall_stats.get('total_revenue') or 0)
    total_orders = int(overall_stats.get('total_orders') or 0)
    total_quantity = int(overall_stats.get('total_quantity') or 0)
    unique_customers = int(overall_stats.get('unique_customers') or 0)
    avg_order_value = (total_revenue / total_orders) if total_orders else 0
    
    # Display KPI metrics
    st.subheader("Key Performance Indicators", divider="blue")
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    
    with kpi1:
        st.metric("Total Revenue", f"${total_revenue:,.2f}")
    with kpi2:
        st.metric("Total Orders", f"{total_orders:,}")
    with kpi3:
        st.metric("Avg Order Value", f"${avg_order_value:,.2f}")
    with kpi4:
        st.metric("Total Items Sold", f"{total_quantity:,}")
    with kpi5:
        st.metric("Unique Customers", f"{unique_customers:,}")
    
    # Revenue trend by date
    st.subheader("Revenue Trend", divider="blue")
    daily_revenue = (
        txns.annotate(date=TruncDate('purchase_date'))
        .values('date')
        .annotate(revenue=Sum(line_total_expr), orders=Count('purchase_id'))
        .order_by('date')
    )
    
    if daily_revenue:
        df_daily = pd.DataFrame(list(daily_revenue))
        df_daily['revenue'] = df_daily['revenue'].astype(float)
        
        fig_revenue = px.line(
            df_daily, x='date', y='revenue',
            title='Daily Revenue',
            labels={'revenue': 'Revenue ($)', 'date': 'Date'}
        )
        fig_revenue.update_traces(line_color='#1f77b4', line_width=3)
        st.plotly_chart(fig_revenue, use_container_width=True)
    
    # Top products and customer segments side by side
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("Top 10 Products", divider="gray")
        top_products = (
            txns.values('product__product_name', 'product__category')
            .annotate(
                revenue=Sum(line_total_expr),
                quantity=Sum('quantity')
            )
            .order_by('-revenue')[:10]
        )
        
        if top_products:
            df_products = pd.DataFrame(list(top_products))
            df_products.columns = ['Product', 'Category', 'Revenue', 'Quantity Sold']
            df_products['Revenue'] = df_products['Revenue'].astype(float)
            
            # Bar chart for top products
            fig_products = px.bar(
                df_products, x='Revenue', y='Product',
                orientation='h',
                title='Top 10 Products by Revenue',
                labels={'Revenue': 'Revenue ($)', 'Product': 'Product'},
                color='Revenue',
                color_continuous_scale='Blues'
            )
            st.plotly_chart(fig_products, use_container_width=True)
            
            # Table view
            st.dataframe(
                df_products.style.format({'Revenue': '${:,.2f}', 'Quantity Sold': '{:,}'}),
                hide_index=True,
                use_container_width=True
            )
    
    with col_right:
        st.subheader("Customer Segments", divider="gray")
        segments = CustomerSegment.objects.all()
        
        if segments.exists():
            segment_stats = segments.values('segment').annotate(
                count=Count('customer'),
                total_monetary=Sum('monetary')
            ).order_by('-total_monetary')
            
            df_segments = pd.DataFrame(list(segment_stats))
            df_segments['total_monetary'] = df_segments['total_monetary'].astype(float)
            
            # Pie chart for segments
            fig_segments = px.pie(
                df_segments,
                values='count',
                names='segment',
                title='Customer Distribution by Segment',
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            st.plotly_chart(fig_segments, use_container_width=True)
            
            # Segment table
            df_segments.columns = ['Segment', 'Customer Count', 'Total Value']
            st.dataframe(
                df_segments.style.format({'Total Value': '${:,.2f}', 'Customer Count': '{:,}'}),
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("No customer segments calculated yet. Run segmentation to see insights.")
    
    # Category performance
    st.subheader("Category Performance", divider="blue")
    category_stats = (
        txns.values('product__category')
        .annotate(
            revenue=Sum(line_total_expr),
            quantity=Sum('quantity'),
            orders=Count('purchase_id')
        )
        .order_by('-revenue')
    )
    
    if category_stats:
        df_categories = pd.DataFrame(list(category_stats))
        df_categories.columns = ['Category', 'Revenue', 'Quantity', 'Orders']
        df_categories['Revenue'] = df_categories['Revenue'].astype(float)
        
        # Horizontal bar chart
        fig_category = px.bar(
            df_categories, x='Revenue', y='Category',
            orientation='h',
            title='Revenue by Category',
            labels={'Revenue': 'Revenue ($)', 'Category': 'Category'},
            color='Revenue',
            color_continuous_scale='Viridis'
        )
        st.plotly_chart(fig_category, use_container_width=True)
        
        st.dataframe(
            df_categories.style.format({'Revenue': '${:,.2f}', 'Quantity': '{:,}', 'Orders': '{:,}'}),
            hide_index=True,
            use_container_width=True
        )
    
    # Geographic distribution
    st.subheader("Sales by Location", divider="blue")
    location_stats = (
        txns.values('customer__city', 'customer__state')
        .annotate(
            revenue=Sum(line_total_expr),
            customers=Count('customer', distinct=True)
        )
        .order_by('-revenue')[:15]
    )
    
    if location_stats:
        df_location = pd.DataFrame(list(location_stats))
        df_location.columns = ['City', 'State', 'Revenue', 'Customers']
        df_location['Revenue'] = df_location['Revenue'].astype(float)
        df_location['Location'] = df_location['City'] + ', ' + df_location['State'].fillna('')
        
        col_map, col_table = st.columns([2, 1])
        
        with col_map:
            fig_location = px.bar(
                df_location, x='Location', y='Revenue',
                title='Top 15 Locations by Revenue',
                labels={'Revenue': 'Revenue ($)', 'Location': 'Location'},
                color='Revenue',
                color_continuous_scale='Teal'
            )
            fig_location.update_xaxes(tickangle=45)
            st.plotly_chart(fig_location, use_container_width=True)
        
        with col_table:
            st.dataframe(
                df_location[['Location', 'Revenue', 'Customers']].style.format({
                    'Revenue': '${:,.2f}',
                    'Customers': '{:,}'
                }),
                hide_index=True,
                use_container_width=True
            )

except Exception as e:
    st.error(f"Error loading sales data: {e}")
    import logging
    logging.exception(e)
