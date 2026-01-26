"""
Confluence Change Detector
Tracks page versions and identifies what's new/changed since last check
"""

import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

load_dotenv()

# Confluence configuration
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_AUTH = (CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)

# Azure Blob Storage for state tracking
STORAGE_CONNECTION_STRING = os.getenv("BLOB_STORAGE_CONNECTION_STRING")
CONTAINER_STATE = os.getenv("BLOB_CONTAINER_STATE", "confluence-state")

# Disable SSL warnings for corporate network
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_blob_service_client():
    """Get Azure Blob Storage client with SSL disabled"""
    return BlobServiceClient.from_connection_string(
        STORAGE_CONNECTION_STRING,
        connection_verify=False
    )


def load_last_check_state(space_key):
    """
    Load the last check state from blob storage
    Returns dict of page_id -> {version, last_modified}
    """
    try:
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(CONTAINER_STATE)
        
        # Try to download existing state
        blob_client = container_client.get_blob_client(f"{space_key}_last_check.json")
        content = blob_client.download_blob().readall()
        state = json.loads(content)
        
        print(f"✅ Loaded last check state: {state['last_check_time']}")
        return state
    
    except Exception as e:
        print(f"⚠️  No previous state found, starting fresh")
        return {
            "space_key": space_key,
            "last_check_time": None,
            "pages": {}
        }


def save_check_state(state):
    """Save current check state to blob storage"""
    try:
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(CONTAINER_STATE)
        
        # Ensure container exists
        try:
            container_client.create_container()
        except:
            pass
        
        # Upload state
        space_key = state['space_key']
        blob_client = container_client.get_blob_client(f"{space_key}_last_check.json")
        
        state['last_check_time'] = datetime.utcnow().isoformat()
        
        blob_client.upload_blob(
            json.dumps(state, indent=2),
            overwrite=True
        )
        
        print(f"✅ Saved check state: {state['last_check_time']}")
        return True
    
    except Exception as e:
        print(f"❌ Failed to save state: {e}")
        return False


def get_recent_pages(space_key, days=7):
    """
    Get all pages updated in the last N days
    """
    print(f"\n{'='*70}")
    print(f"CHECKING FOR UPDATES IN SPACE: {space_key}")
    print(f"{'='*70}\n")
    
    # Calculate date threshold
    since_date = datetime.utcnow() - timedelta(days=days)
    since_str = since_date.strftime("%Y-%m-%d")
    
    print(f"📅 Looking for changes since: {since_str}")
    
    # Use CQL (Confluence Query Language) to find recently updated pages
    url = f"{CONFLUENCE_URL}/rest/api/content/search"
    params = {
        "cql": f"space={space_key} AND lastModified>='{since_str}' order by lastModified desc",
        "expand": "version,history.lastUpdated",
        "limit": 100
    }
    
    try:
        response = requests.get(url, auth=CONFLUENCE_AUTH, params=params, verify=False)
        response.raise_for_status()
        data = response.json()
        
        pages = data.get('results', [])
        print(f"✅ Found {len(pages)} pages modified in last {days} days\n")
        
        return pages
    
    except Exception as e:
        print(f"❌ Error fetching pages: {e}")
        return []


def detect_changes(space_key, days=7):
    """
    Detect what's new and what's changed in the space
    
    Returns:
        {
            'new_pages': [...],
            'updated_pages': [...],
            'summary': {...}
        }
    """
    # Load previous state
    last_state = load_last_check_state(space_key)
    previous_pages = last_state.get('pages', {})
    
    # Get recent pages
    recent_pages = get_recent_pages(space_key, days)
    
    new_pages = []
    updated_pages = []
    
    print("📊 CHANGE ANALYSIS:\n")
    
    for page in recent_pages:
        page_id = page['id']
        current_version = page['version']['number']
        last_modified = page['version']['when']
        title = page['title']
        
        # Check if this is a new page or an update
        if page_id not in previous_pages:
            new_pages.append({
                'id': page_id,
                'title': title,
                'version': current_version,
                'last_modified': last_modified,
                'url': f"{CONFLUENCE_URL}/wiki{page['_links']['webui']}"
            })
            print(f"🆕 NEW: {title} (v{current_version})")
        
        else:
            prev_version = previous_pages[page_id].get('version', 0)
            if current_version > prev_version:
                updated_pages.append({
                    'id': page_id,
                    'title': title,
                    'version': current_version,
                    'previous_version': prev_version,
                    'last_modified': last_modified,
                    'url': f"{CONFLUENCE_URL}/wiki{page['_links']['webui']}"
                })
                print(f"✏️  UPDATED: {title} (v{prev_version} → v{current_version})")
    
    # Update state with current versions
    current_state = {
        'space_key': space_key,
        'pages': {}
    }
    
    for page in recent_pages:
        current_state['pages'][page['id']] = {
            'title': page['title'],
            'version': page['version']['number'],
            'last_modified': page['version']['when']
        }
    
    # Save updated state
    save_check_state(current_state)
    
    print(f"\n{'='*70}")
    print(f"SUMMARY:")
    print(f"  🆕 New pages: {len(new_pages)}")
    print(f"  ✏️  Updated pages: {len(updated_pages)}")
    print(f"{'='*70}\n")
    
    return {
        'new_pages': new_pages,
        'updated_pages': updated_pages,
        'summary': {
            'total_new': len(new_pages),
            'total_updated': len(updated_pages),
            'space_key': space_key,
            'check_time': datetime.utcnow().isoformat()
        }
    }


if __name__ == "__main__":
    import sys
    
    # Default to CIPPMOPF space
    space_key = sys.argv[1] if len(sys.argv) > 1 else "CIPPMOPF"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    
    changes = detect_changes(space_key, days)
    
    # Save results to file
    output_file = f"data/changes_{space_key}_{datetime.utcnow().strftime('%Y%m%d')}.json"
    os.makedirs("data", exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(changes, f, indent=2)
    
    print(f"✅ Changes saved to: {output_file}")
