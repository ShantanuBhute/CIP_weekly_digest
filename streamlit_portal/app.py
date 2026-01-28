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
        now = datetime.utcnow().isoformat()
        subscription = {
            "id": email.lower().replace("@", "_at_").replace(".", "_"),
            "partitionKey": "subscriptions",
            "email": email.lower(),
            "displayName": name,
            "isVerified": False,
            "subscriptions": [
                {
                    "pageId": page_id,
                    "pageName": AVAILABLE_PAGES[page_id]["name"],
                    "subscribedAt": now
                }
                for page_id in page_ids if page_id in AVAILABLE_PAGES
            ],
            "preferences": {
                "frequency": "immediate",
                "digestFormat": "html"
            },
            "createdAt": now,
            "updatedAt": now
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
            now = datetime.utcnow().isoformat()
            
            # Build subscriptions list preserving existing timestamps
            current_subs = {s['pageId']: s for s in existing.get('subscriptions', [])}
            
            new_subscriptions = []
            for page_id in page_ids:
                if page_id in AVAILABLE_PAGES:
                    if page_id in current_subs:
                        # Keep existing subscription with original timestamp
                        new_subscriptions.append(current_subs[page_id])
                    else:
                        # New subscription
                        new_subscriptions.append({
                            "pageId": page_id,
                            "pageName": AVAILABLE_PAGES[page_id]["name"],
                            "subscribedAt": now
                        })
            
            existing['subscriptions'] = new_subscriptions
            existing['updatedAt'] = now
            container.upsert_item(existing)
            return True
        return False
    except Exception as e:
        st.error(f"Error updating subscription: {e}")
        return False


def unsubscribe_all(email: str) -> bool:
    """Unsubscribe user from all pages"""
    container = get_cosmos_client()
    if not container:
        return False
    try:
        existing = get_subscription(email)
        if existing:
            # Delete the subscription document
            container.delete_item(item=existing["id"], partition_key="subscriptions")
            return True
        return False
    except Exception as e:
        st.error(f"Error unsubscribing: {e}")
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
    
    st.divider()
    
    # User identification
    st.subheader("👤 Your Information")
    
    col1, col2 = st.columns(2)
    with col1:
        email = st.text_input(
            "Email Address", 
            placeholder="john.doe@eaton.com",
            help="Enter your corporate email address"
        )
    with col2:
        name = st.text_input(
            "Display Name", 
            placeholder="John Doe",
            help="Your name as it will appear in emails"
        )
    
    st.divider()
    
    # Load existing subscription
    existing_sub = None
    existing_pages = []
    if email and container:
        existing_sub = get_subscription(email)
        if existing_sub:
            # Extract page IDs from the subscriptions array
            existing_pages = [s['pageId'] for s in existing_sub.get('subscriptions', [])]
            name = existing_sub.get('displayName', name)  # Pre-fill name from existing subscription
    
    # Page selection
    st.subheader("📄 Available Pages")
    st.markdown("Select the pages you want to receive email updates for:")
    
    selected_pages = []
    for page_id, page_info in AVAILABLE_PAGES.items():
        is_checked = page_id in existing_pages
        col1, col2 = st.columns([0.1, 0.9])
        with col1:
            checked = st.checkbox(
                "Select",
                value=is_checked,
                key=f"page_{page_id}",
                label_visibility="collapsed"
            )
        with col2:
            st.markdown(f"""
            <div class="page-card">
                <strong>{page_info['icon']} {page_info['name']}</strong><br>
                <small style="color: #666;">{page_info['description']}</small><br>
                <small style="color: #999;">Page ID: {page_id} | Space: {page_info['space']}</small>
            </div>
            """, unsafe_allow_html=True)
        
        if checked:
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
        if container:
            load_btn = st.button("📥 Load My Settings", use_container_width=True)
        else:
            load_btn = False
    
    with col3:
        if container:
            unsub_btn = st.button("🚫 Unsubscribe All", use_container_width=True)
        else:
            unsub_btn = False
    
    # Handle Save
    if save_btn:
        if not email:
            st.error("❌ Please enter your email address")
        elif not name:
            st.error("❌ Please enter your display name")
        elif not selected_pages:
            st.error("❌ Please select at least one page")
        elif "@" not in email:
            st.error("❌ Please enter a valid email address")
        else:
            if container:
                try:
                    if existing_sub:
                        success = update_subscription(email, selected_pages)
                        if success:
                            st.success(f"""
                            ✅ **Subscription updated successfully!**
                            
                            You will receive email updates when any of your {len(selected_pages)} subscribed pages are updated.
                            """)
                    else:
                        success = create_subscription(email, name, selected_pages)
                        if success:
                            st.success(f"""
                            ✅ **Subscription saved successfully!**
                            
                            You will receive email updates when any of your {len(selected_pages)} subscribed pages are updated.
                            """)
                            st.balloons()
                except Exception as e:
                    st.error(f"❌ Error saving subscription: {e}")
            else:
                # Demo mode
                st.warning("Demo mode: Subscription not saved (Cosmos DB not configured)")
                st.info(f"""
                **Would save:**
                - Email: {email}
                - Name: {name}
                - Pages: {', '.join([AVAILABLE_PAGES[p]['name'] for p in selected_pages])}
                """)
    
    # Handle Load
    if load_btn and email:
        if existing_sub:
            subscriptions = existing_sub.get('subscriptions', [])
            st.success(f"""
            📥 **Found your subscription!**
            
            - **Name:** {existing_sub.get('displayName', 'N/A')}
            - **Subscribed pages:** {len(subscriptions)}
            - **Created:** {existing_sub.get('createdAt', 'N/A')[:10]}
            - **Last updated:** {existing_sub.get('updatedAt', 'N/A')[:10]}
            """)
            for sub in subscriptions:
                page_id = sub.get('pageId')
                page_name = sub.get('pageName', page_id)
                subscribed_at = sub.get('subscribedAt', 'N/A')[:10]
                icon = AVAILABLE_PAGES.get(page_id, {}).get('icon', '📄')
                st.markdown(f"  ✅ {icon} **{page_name}** (subscribed: {subscribed_at})")
        else:
            st.info("ℹ️ No subscription found for this email address")
    
    # Handle Unsubscribe
    if unsub_btn and email:
        if 'confirm_unsub' not in st.session_state:
            st.session_state['confirm_unsub'] = False
        
        if st.session_state.get('confirm_unsub'):
            try:
                success = unsubscribe_all(email)
                if success:
                    st.success("✅ You have been unsubscribed from all pages")
                    st.session_state['confirm_unsub'] = False
                    # Clear the form
                    st.rerun()
                else:
                    st.info("ℹ️ No subscription found to remove")
                    st.session_state['confirm_unsub'] = False
            except Exception as e:
                st.error(f"❌ Error unsubscribing: {e}")
        else:
            st.warning("⚠️ Click 'Unsubscribe All' again to confirm removal of all subscriptions")
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
