import os
import json
import sys
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import urllib3

# Disable SSL warnings (for corporate networks with self-signed certs)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables from .env file
load_dotenv()

confluence_url = os.getenv("CONFLUENCE_URL")
api_token = os.getenv("CONFLUENCE_API_TOKEN")
email = os.getenv("CONFLUENCE_EMAIL")

if not all([confluence_url, api_token]):
    print("Missing required environment variables (CONFLUENCE_URL, CONFLUENCE_API_TOKEN)")
    sys.exit(1)

# Test 1: List all Confluence spaces
print("=" * 70)
print("TEST 1: List all Confluence spaces")
print("=" * 70)

try:
    url = f"{confluence_url}/rest/api/space"
    headers = {"Accept": "application/json"}
    auth = HTTPBasicAuth(email, api_token) if email else HTTPBasicAuth("", api_token)
    
    response = requests.get(url, headers=headers, auth=auth, timeout=30, verify=False)
    
    if response.ok:
        data = response.json()
        spaces = data.get("results", [])
        print(f"✅ Connection successful!")
        print(f"📦 Found {len(spaces)} spaces:")
        print()
        
        for space in spaces[:10]:  # Show first 10
            key = space.get("key", "N/A")
            name = space.get("name", "N/A")
            space_url = f"{confluence_url}/spaces/{key}"
            print(f"  🔹 {key:<15} - {name}")
            print(f"     URL: {space_url}")
        
        if len(spaces) > 10:
            print(f"\n  ... and {len(spaces) - 10} more spaces")
    else:
        print(f"❌ Failed to list spaces. Status: {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)
        
except requests.exceptions.RequestException as e:
    print(f"❌ Network error: {e}")
    sys.exit(1)

# Test 2: Get pages from a specific space (CIPPMOPF)
print("\n" + "=" * 70)
print("TEST 2: Get pages from CIPPMOPF space")
print("=" * 70)

try:
    space_key = "CIPPMOPF"
    url = f"{confluence_url}/rest/api/space/{space_key}/content/page"
    
    response = requests.get(url, headers=headers, auth=auth, timeout=30, verify=False)
    
    if response.ok:
        data = response.json()
        pages = data.get("results", [])
        print(f"✅ Found {len(pages)} pages in {space_key} space:")
        print()
        
        for page in pages[:5]:  # Show first 5
            title = page.get("title", "N/A")
            page_id = page.get("id", "N/A")
            print(f"  📄 {title}")
            print(f"     ID: {page_id}")
        
        if len(pages) > 5:
            print(f"\n  ... and {len(pages) - 5} more pages")
    else:
        print(f"⚠️ Could not get pages from {space_key}. Status: {response.status_code}")
        
except requests.exceptions.RequestException as e:
    print(f"❌ Network error: {e}")

# Test 3: Get a specific page
print("\n" + "=" * 70)
print("TEST 3: Get specific page (JIRA - EASE Requirements)")
print("=" * 70)

try:
    page_id = "304254123"
    url = f"{confluence_url}/rest/api/content/{page_id}"
    params = {"expand": "body.storage,version,space"}
    
    response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30, verify=False)
    
    if response.ok:
        page = response.json()
        print(f"✅ Successfully retrieved page:")
        print()
        print(f"  📄 Title: {page.get('title', 'N/A')}")
        print(f"  🔑 ID: {page.get('id', 'N/A')}")
        print(f"  📁 Space: {page.get('space', {}).get('name', 'N/A')}")
        print(f"  🔗 URL: {confluence_url}/spaces/{page.get('space', {}).get('key', '')}/pages/{page_id}/{page.get('title', '').replace(' ', '+')}")
        print(f"  📋 Version: {page.get('version', {}).get('number', 'N/A')}")
        
        # Show content preview
        content = page.get("body", {}).get("storage", {}).get("value", "")
        if content:
            # Strip HTML tags for preview
            import re
            clean_content = re.sub('<.*?>', '', content)
            preview = clean_content[:500].strip()
            print(f"\n  📝 Content preview (first 500 chars):")
            print(f"  {preview}...")
    else:
        print(f"⚠️ Could not get page. Status: {response.status_code}")
        print(f"Response: {response.text}")
        
except requests.exceptions.RequestException as e:
    print(f"❌ Network error: {e}")

print("\n" + "=" * 70)
print("✅ Testing complete!")
print("=" * 70)
