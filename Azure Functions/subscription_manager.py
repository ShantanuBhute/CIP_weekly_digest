"""
Subscription Manager for Confluence Digest
Manages user subscriptions to page updates using Azure Cosmos DB
"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Cosmos DB configuration
COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
COSMOS_KEY = os.getenv("COSMOS_KEY")
COSMOS_DATABASE = os.getenv("COSMOS_DATABASE", "confluence-digest")
COSMOS_CONTAINER = os.getenv("COSMOS_CONTAINER", "subscriptions")

# Available pages for subscription (your 4 pages)
AVAILABLE_PAGES = {
    "164168599": {
        "name": "ProPM Roles & Responsibilities",
        "space": "CIPPMOPF",
        "description": "Project Management roles and responsibilities documentation"
    },
    "166041865": {
        "name": "Agile - Scrum Roles & Responsibilities", 
        "space": "CIPPMOPF",
        "description": "Scrum team roles and responsibilities for Agile projects"
    },
    "17386855": {
        "name": "RACI",
        "space": "CIPPMOPF", 
        "description": "RACI matrix - Responsible, Accountable, Consulted, Informed"
    },
    "439124075": {
        "name": "EMPower AI Research",
        "space": "CIPPMOPF",
        "description": "EMPower AI research documentation and findings"
    }
}


def get_cosmos_client():
    """Get Cosmos DB container client"""
    try:
        from azure.cosmos import CosmosClient, PartitionKey
        
        client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
        database = client.create_database_if_not_exists(id=COSMOS_DATABASE)
        container = database.create_container_if_not_exists(
            id=COSMOS_CONTAINER,
            partition_key=PartitionKey(path="/partitionKey"),
            offer_throughput=400  # Minimum RU/s for serverless
        )
        return container
    except Exception as e:
        print(f"❌ Cosmos DB connection failed: {e}")
        raise


def get_subscription(email: str) -> dict:
    """Get a user's subscription record"""
    container = get_cosmos_client()
    
    try:
        # Query by email
        query = "SELECT * FROM c WHERE c.email = @email"
        items = list(container.query_items(
            query=query,
            parameters=[{"name": "@email", "value": email.lower()}],
            enable_cross_partition_query=True
        ))
        
        if items:
            return items[0]
        return None
    except Exception as e:
        print(f"❌ Error getting subscription: {e}")
        return None


def create_or_update_subscription(email: str, display_name: str, subscribed_pages: list) -> dict:
    """
    Create or update a user's subscription.
    
    Args:
        email: User's email address
        display_name: User's display name
        subscribed_pages: List of page_ids to subscribe to
        
    Returns:
        Updated subscription document
    """
    container = get_cosmos_client()
    email_lower = email.lower()
    
    # Get existing subscription
    existing = get_subscription(email_lower)
    
    now = datetime.utcnow().isoformat()
    
    if existing:
        # Update existing subscription
        doc_id = existing['id']
        
        # Build subscriptions list
        current_subs = {s['pageId']: s for s in existing.get('subscriptions', [])}
        
        new_subscriptions = []
        for page_id in subscribed_pages:
            if page_id in AVAILABLE_PAGES:
                if page_id in current_subs:
                    # Keep existing subscription date
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
        existing['displayName'] = display_name
        
        container.upsert_item(existing)
        return existing
    else:
        # Create new subscription
        doc = {
            "id": email_lower.replace("@", "_at_").replace(".", "_"),
            "partitionKey": "subscriptions",
            "email": email_lower,
            "displayName": display_name,
            "ssoVerified": False,  # Will be set true after SSO verification
            "subscriptions": [
                {
                    "pageId": page_id,
                    "pageName": AVAILABLE_PAGES[page_id]["name"],
                    "subscribedAt": now
                }
                for page_id in subscribed_pages if page_id in AVAILABLE_PAGES
            ],
            "preferences": {
                "frequency": "immediate",  # immediate, daily, weekly
                "digestFormat": "html"
            },
            "createdAt": now,
            "updatedAt": now
        }
        
        container.create_item(doc)
        return doc


def unsubscribe_from_page(email: str, page_id: str) -> bool:
    """Remove a single page subscription"""
    existing = get_subscription(email.lower())
    
    if not existing:
        return False
    
    container = get_cosmos_client()
    
    existing['subscriptions'] = [
        s for s in existing.get('subscriptions', [])
        if s['pageId'] != page_id
    ]
    existing['updatedAt'] = datetime.utcnow().isoformat()
    
    container.upsert_item(existing)
    return True


def unsubscribe_all(email: str) -> bool:
    """Remove all subscriptions for a user"""
    existing = get_subscription(email.lower())
    
    if not existing:
        return False
    
    container = get_cosmos_client()
    container.delete_item(item=existing['id'], partition_key="subscriptions")
    return True


def get_subscribers_for_page(page_id: str) -> list:
    """
    Get all users subscribed to a specific page.
    Used when sending email notifications.
    
    Returns:
        List of dicts with 'email' and 'displayName'
    """
    container = get_cosmos_client()
    
    query = """
    SELECT c.email, c.displayName, c.preferences
    FROM c 
    WHERE ARRAY_CONTAINS(c.subscriptions, {"pageId": @pageId}, true)
    """
    
    items = list(container.query_items(
        query=query,
        parameters=[{"name": "@pageId", "value": page_id}],
        enable_cross_partition_query=True
    ))
    
    return items


def get_all_subscribers() -> list:
    """Get all subscribers (for admin view)"""
    container = get_cosmos_client()
    
    query = "SELECT * FROM c WHERE c.partitionKey = 'subscriptions'"
    items = list(container.query_items(
        query=query,
        enable_cross_partition_query=True
    ))
    
    return items


def get_available_pages() -> dict:
    """Get all available pages for subscription"""
    return AVAILABLE_PAGES


def verify_sso(email: str) -> bool:
    """Mark user as SSO verified"""
    existing = get_subscription(email.lower())
    
    if not existing:
        return False
    
    container = get_cosmos_client()
    existing['ssoVerified'] = True
    existing['ssoVerifiedAt'] = datetime.utcnow().isoformat()
    container.upsert_item(existing)
    return True


# ===== Test Functions =====
if __name__ == "__main__":
    print("Testing Subscription Manager...")
    
    # Test creating a subscription
    print("\n1. Creating subscription for test user...")
    result = create_or_update_subscription(
        email="test.user@eaton.com",
        display_name="Test User",
        subscribed_pages=["164168599", "166041865"]
    )
    print(f"   Created: {result['email']} with {len(result['subscriptions'])} subscriptions")
    
    # Test getting subscription
    print("\n2. Getting subscription...")
    sub = get_subscription("test.user@eaton.com")
    print(f"   Found: {sub['email']}")
    print(f"   Pages: {[s['pageName'] for s in sub['subscriptions']]}")
    
    # Test getting subscribers for a page
    print("\n3. Getting subscribers for page 164168599...")
    subscribers = get_subscribers_for_page("164168599")
    print(f"   Found {len(subscribers)} subscribers")
    for s in subscribers:
        print(f"   - {s['email']}")
    
    # Test available pages
    print("\n4. Available pages:")
    for page_id, info in get_available_pages().items():
        print(f"   - {page_id}: {info['name']}")
    
    print("\n✅ All tests passed!")
