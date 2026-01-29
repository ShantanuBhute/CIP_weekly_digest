"""
CIP Digest Subscription Portal - Streamlit App
A simple UI for managing email subscriptions to Confluence page updates
"""

import streamlit as st
import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load settings from local.settings.json
settings_path = os.path.join(os.path.dirname(__file__), "local.settings.json")
if os.path.exists(settings_path):
    with open(settings_path, "r") as f:
        settings = json.load(f)
        for key, value in settings.get("Values", {}).items():
            os.environ.setdefault(key, value)

from dotenv import load_dotenv
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="CIP Digest Subscriptions",
    page_icon="📧",
    layout="centered"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f4e79;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .page-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
        border-left: 4px solid #1f4e79;
    }
    .success-box {
        background-color: #d4edda;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Available pages (same as in subscription_manager.py)
AVAILABLE_PAGES = {
    "164168599": {
        "name": "ProPM Roles & Responsibilities",
        "space": "CIPPMOPF",
        "description": "Project Management roles and responsibilities documentation",
        "icon": "👥"
    },
    "166041865": {
        "name": "Agile - Scrum Roles & Responsibilities", 
        "space": "CIPPMOPF",
        "description": "Scrum team roles and responsibilities for Agile projects",
        "icon": "🔄"
    },
    "17386855": {
        "name": "RACI",
        "space": "CIPPMOPF", 
        "description": "RACI matrix - Responsible, Accountable, Consulted, Informed",
        "icon": "📋"
    },
    "439124075": {
        "name": "EMPower AI Research",
        "space": "CIPPMOPF",
        "description": "EMPower AI research documentation and findings",
        "icon": "🤖"
    }
}


def check_cosmos_connection():
    """Check if Cosmos DB is configured and accessible"""
    try:
        from subscription_manager import get_cosmos_client
        get_cosmos_client()
        return True
    except Exception as e:
        return False


def main():
    # Header
    st.markdown('<p class="main-header">📧 CIP Digest Subscriptions</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Subscribe to receive email updates when Confluence pages change</p>', unsafe_allow_html=True)
    
    # Check Cosmos DB connection
    cosmos_connected = check_cosmos_connection()
    
    if not cosmos_connected:
        st.warning("""
        ⚠️ **Cosmos DB not configured yet**
        
        Running in demo mode. To enable full functionality:
        1. Create Cosmos DB in Azure Portal
        2. Add these to your `.env` file:
        ```
        COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
        COSMOS_KEY=your-primary-key
        COSMOS_DATABASE=confluence-digest
        COSMOS_CONTAINER=subscriptions
        ```
        3. Restart this app
        """)
    
    st.divider()
    
    # User Input Section
    st.subheader("👤 Your Information")
    
    col1, col2 = st.columns(2)
    with col1:
        email = st.text_input(
            "Email Address",
            placeholder="john.doe@eaton.com",
            help="Enter your corporate email address"
        )
    with col2:
        display_name = st.text_input(
            "Display Name",
            placeholder="John Doe",
            help="Your name as it will appear in emails"
        )
    
    st.divider()
    
    # Page Selection
    st.subheader("📄 Available Pages")
    st.markdown("Select the pages you want to receive email updates for:")
    
    selected_pages = []
    
    for page_id, info in AVAILABLE_PAGES.items():
        col1, col2 = st.columns([0.1, 0.9])
        with col1:
            selected = st.checkbox("Select", key=f"page_{page_id}", label_visibility="collapsed")
        with col2:
            st.markdown(f"""
            <div class="page-card">
                <strong>{info['icon']} {info['name']}</strong><br>
                <small style="color: #666;">{info['description']}</small><br>
                <small style="color: #999;">Page ID: {page_id} | Space: {info['space']}</small>
            </div>
            """, unsafe_allow_html=True)
        
        if selected:
            selected_pages.append(page_id)
    
    st.divider()
    
    # Summary
    st.subheader("📋 Subscription Summary")
    
    if selected_pages:
        st.success(f"✅ You have selected **{len(selected_pages)} page(s)** for email notifications:")
        for page_id in selected_pages:
            st.markdown(f"  - {AVAILABLE_PAGES[page_id]['icon']} {AVAILABLE_PAGES[page_id]['name']}")
    else:
        st.info("ℹ️ No pages selected. Select at least one page to receive email updates.")
    
    st.divider()
    
    # Action Buttons
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        save_btn = st.button("💾 Save Preferences", type="primary", use_container_width=True)
    
    with col2:
        if cosmos_connected:
            load_btn = st.button("📥 Load My Settings", use_container_width=True)
        else:
            load_btn = False
    
    with col3:
        if cosmos_connected:
            unsub_btn = st.button("🚫 Unsubscribe All", use_container_width=True)
        else:
            unsub_btn = False
    
    # Handle Save
    if save_btn:
        if not email:
            st.error("❌ Please enter your email address")
        elif not display_name:
            st.error("❌ Please enter your display name")
        elif not selected_pages:
            st.error("❌ Please select at least one page")
        elif "@" not in email:
            st.error("❌ Please enter a valid email address")
        else:
            if cosmos_connected:
                try:
                    from subscription_manager import create_or_update_subscription
                    result = create_or_update_subscription(email, display_name, selected_pages)
                    st.success(f"""
                    ✅ **Subscription saved successfully!**
                    
                    You will receive email updates when any of your {len(selected_pages)} subscribed pages are updated.
                    """)
                    st.balloons()
                except Exception as e:
                    st.error(f"❌ Error saving subscription: {e}")
            else:
                # Demo mode - just show success
                st.success(f"""
                ✅ **Demo Mode - Subscription Preview**
                
                In production, this would save:
                - Email: {email}
                - Name: {display_name}
                - Pages: {', '.join([AVAILABLE_PAGES[p]['name'] for p in selected_pages])}
                """)
    
    # Handle Load
    if load_btn and email:
        try:
            from subscription_manager import get_subscription
            sub = get_subscription(email)
            if sub:
                st.success(f"""
                📥 **Found your subscription!**
                
                - **Name:** {sub.get('displayName', 'N/A')}
                - **Subscribed pages:** {len(sub.get('subscriptions', []))}
                - **Created:** {sub.get('createdAt', 'N/A')[:10]}
                """)
                for s in sub.get('subscriptions', []):
                    st.markdown(f"  ✅ {s.get('pageName', s.get('pageId'))}")
            else:
                st.info("ℹ️ No subscription found for this email address")
        except Exception as e:
            st.error(f"❌ Error loading subscription: {e}")
    
    # Handle Unsubscribe
    if unsub_btn and email:
        if st.session_state.get('confirm_unsub'):
            try:
                from subscription_manager import unsubscribe_all
                unsubscribe_all(email)
                st.success("✅ You have been unsubscribed from all pages")
                st.session_state['confirm_unsub'] = False
            except Exception as e:
                st.error(f"❌ Error unsubscribing: {e}")
        else:
            st.warning("⚠️ Click 'Unsubscribe All' again to confirm")
            st.session_state['confirm_unsub'] = True
    
    # Footer
    st.divider()
    st.markdown("""
    <div style="text-align: center; color: #999; font-size: 0.8rem;">
        CIP Digest Subscription Portal | Powered by Azure Cosmos DB & Azure Functions<br>
        Emails are generated automatically when Confluence pages are updated
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
