"""
CIP Digest Subscription Portal - Streamlit App
A simple UI for managing email subscriptions to Confluence page updates
"""

import streamlit as st
import os
from datetime import datetime
from azure.cosmos import CosmosClient, PartitionKey

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
        color: #00796b;
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
        background-color: #f1f8f6;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
        border-left: 4px solid #00796b;
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

# Available pages
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

# Cosmos DB Configuration (from Streamlit secrets)
COSMOS_ENDPOINT = st.secrets.get("COSMOS_ENDPOINT", os.getenv("COSMOS_ENDPOINT", ""))
COSMOS_KEY = st.secrets.get("COSMOS_KEY", os.getenv("COSMOS_KEY", ""))
COSMOS_DATABASE = st.secrets.get("COSMOS_DATABASE", os.getenv("COSMOS_DATABASE", "confluence-digest"))
COSMOS_CONTAINER = st.secrets.get("COSMOS_CONTAINER", os.getenv("COSMOS_CONTAINER", "subscriptions"))


@st.cache_resource
def get_cosmos_client():
    """Get Cosmos DB container client (cached)"""
    if not COSMOS_ENDPOINT or not COSMOS_KEY:
        return None
    try:
        client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
        database = client.create_database_if_not_exists(id=COSMOS_DATABASE)
        container = database.create_container_if_not_exists(
            id=COSMOS_CONTAINER,
            partition_key=PartitionKey(path="/partitionKey"),
            offer_throughput=400
        )
        return container
    except Exception as e:
        st.error(f"Cosmos DB connection failed: {e}")
        return None


def get_subscription(email: str) -> dict:
    """Get a user's subscription record"""
    container = get_cosmos_client()
    if not container:
        return None
    try:
        query = "SELECT * FROM c WHERE c.email = @email"
        items = list(container.query_items(
            query=query,
            parameters=[{"name": "@email", "value": email.lower()}],
            enable_cross_partition_query=True
        ))
        return items[0] if items else None
    except Exception as e:
        st.error(f"Error getting subscription: {e}")
        return None


def create_subscription(email: str, name: str, page_ids: list) -> bool:
    """Create a new subscription"""
    container = get_cosmos_client()
    if not container:
        return False
    try:
        subscription = {
            "id": email.lower().replace("@", "_at_").replace(".", "_"),
            "partitionKey": "subscription",
            "email": email.lower(),
            "name": name,
            "subscribed_pages": page_ids,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "is_active": True
        }
        container.upsert_item(subscription)
        return True
    except Exception as e:
        st.error(f"Error creating subscription: {e}")
        return False


def update_subscription(email: str, page_ids: list) -> bool:
    """Update subscription page list"""
    container = get_cosmos_client()
    if not container:
        return False
    try:
        existing = get_subscription(email)
        if existing:
            existing["subscribed_pages"] = page_ids
            existing["updated_at"] = datetime.utcnow().isoformat()
            container.upsert_item(existing)
            return True
        return False
    except Exception as e:
        st.error(f"Error updating subscription: {e}")
        return False


def main():
    # Header
    st.markdown('<p class="main-header">📧 CIP Digest Subscriptions</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Subscribe to receive email updates when Confluence pages change</p>', unsafe_allow_html=True)
    
    # Check Cosmos DB connection
    container = get_cosmos_client()
    
    if not container:
        st.warning("""
        ⚠️ **Cosmos DB not configured**
        
        Please configure the following secrets in Streamlit Cloud:
        - `COSMOS_ENDPOINT`
        - `COSMOS_KEY`
        - `COSMOS_DATABASE`
        - `COSMOS_CONTAINER`
        """)
        st.info("Running in demo mode - subscriptions will not be saved.")
    
    # User identification
    st.subheader("📝 Your Information")
    
    col1, col2 = st.columns(2)
    with col1:
        email = st.text_input("Email Address", placeholder="your.email@eaton.com")
    with col2:
        name = st.text_input("Your Name", placeholder="John Doe")
    
    # Load existing subscription
    existing_sub = None
    existing_pages = []
    if email and container:
        existing_sub = get_subscription(email)
        if existing_sub:
            existing_pages = existing_sub.get("subscribed_pages", [])
            st.success(f"✅ Found existing subscription for {email}")
    
    # Page selection
    st.subheader("📄 Select Pages to Monitor")
    st.markdown("Choose which Confluence pages you want to receive update notifications for:")
    
    selected_pages = []
    for page_id, page_info in AVAILABLE_PAGES.items():
        is_checked = page_id in existing_pages
        col1, col2 = st.columns([1, 10])
        with col1:
            checked = st.checkbox(
                page_info["icon"],
                value=is_checked,
                key=f"page_{page_id}",
                label_visibility="collapsed"
            )
        with col2:
            st.markdown(f"""
            <div class="page-card">
                <strong>{page_info['icon']} {page_info['name']}</strong><br>
                <small style="color: #666;">{page_info['description']}</small>
            </div>
            """, unsafe_allow_html=True)
        
        if checked:
            selected_pages.append(page_id)
    
    # Subscribe button
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("💾 Save Subscription", type="primary", use_container_width=True):
            if not email:
                st.error("Please enter your email address")
            elif not name:
                st.error("Please enter your name")
            elif not selected_pages:
                st.error("Please select at least one page to monitor")
            elif not container:
                st.warning("Demo mode: Subscription not saved (Cosmos DB not configured)")
                st.info(f"Would subscribe {email} to {len(selected_pages)} page(s)")
            else:
                if existing_sub:
                    success = update_subscription(email, selected_pages)
                    if success:
                        st.success(f"✅ Subscription updated! You're now monitoring {len(selected_pages)} page(s).")
                else:
                    success = create_subscription(email, name, selected_pages)
                    if success:
                        st.success(f"✅ Subscribed! You'll receive emails when selected pages change.")
                        st.balloons()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #999; font-size: 0.8rem;">
        CIP Digest Subscription Portal | Powered by Azure Cosmos DB & Streamlit<br>
        Questions? Contact the CIP team.
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
