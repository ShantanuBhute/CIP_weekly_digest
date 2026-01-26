"""
Confluence Explorer - Find and explore the ARCHIVED space/pages
Step 1: Find the 'ARCHIVED - To be deleted' page and its sub-pages
"""

import os
import json
import sys
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

confluence_url = os.getenv("CONFLUENCE_URL")
api_token = os.getenv("CONFLUENCE_API_TOKEN")
email = os.getenv("CONFLUENCE_EMAIL")

if not all([confluence_url, api_token]):
    print("Missing required environment variables")
    sys.exit(1)

headers = {"Accept": "application/json"}
auth = HTTPBasicAuth(email, api_token) if email else HTTPBasicAuth("", api_token)


def search_pages(query, limit=25):
    """Search for pages using CQL"""
    url = f"{confluence_url}/rest/api/content/search"
    params = {
        "cql": f'text ~ "{query}" OR title ~ "{query}"',
        "limit": limit,
        "expand": "space,ancestors"
    }
    response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30, verify=False)
    return response.json() if response.ok else None


def get_page_children(page_id, limit=100):
    """Get child pages of a given page"""
    url = f"{confluence_url}/rest/api/content/{page_id}/child/page"
    params = {"limit": limit, "expand": "version,space"}
    response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30, verify=False)
    return response.json() if response.ok else None


def get_page_by_title(space_key, title):
    """Get a page by its title in a specific space"""
    url = f"{confluence_url}/rest/api/content"
    params = {
        "spaceKey": space_key,
        "title": title,
        "expand": "body.storage,version,space,ancestors,children.page"
    }
    response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30, verify=False)
    return response.json() if response.ok else None


def get_page_with_attachments(page_id):
    """Get page content including attachments"""
    url = f"{confluence_url}/rest/api/content/{page_id}"
    params = {
        "expand": "body.storage,version,space,ancestors,children.page,children.attachment"
    }
    response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30, verify=False)
    return response.json() if response.ok else None


def get_page_attachments(page_id):
    """Get all attachments for a page"""
    url = f"{confluence_url}/rest/api/content/{page_id}/child/attachment"
    params = {"expand": "version,metadata"}
    response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30, verify=False)
    return response.json() if response.ok else None


def print_page_tree(page_id, indent=0):
    """Recursively print page tree"""
    page = get_page_with_attachments(page_id)
    if not page:
        return
    
    prefix = "  " * indent
    print(f"{prefix}📄 {page.get('title', 'N/A')}")
    print(f"{prefix}   ID: {page.get('id')}")
    print(f"{prefix}   Version: {page.get('version', {}).get('number', 'N/A')}")
    
    # Check for attachments
    attachments = page.get('children', {}).get('attachment', {}).get('results', [])
    if attachments:
        print(f"{prefix}   📎 Attachments: {len(attachments)}")
        for att in attachments:
            att_title = att.get('title', 'N/A')
            att_size = att.get('extensions', {}).get('fileSize', 'N/A')
            media_type = att.get('metadata', {}).get('mediaType', 'unknown')
            print(f"{prefix}      - {att_title} ({media_type})")
    
    # Get children
    children = page.get('children', {}).get('page', {}).get('results', [])
    if children:
        print(f"{prefix}   📁 Sub-pages: {len(children)}")
        for child in children:
            print_page_tree(child.get('id'), indent + 2)


# ============================================================
# STEP 1: Search for "ARCHIVED - To be deleted" page
# ============================================================
print("=" * 70)
print("STEP 1: Searching for 'ARCHIVED - To be deleted' page")
print("=" * 70)

search_result = search_pages("ARCHIVED - To be deleted")
if search_result:
    results = search_result.get("results", [])
    print(f"Found {len(results)} matching pages:\n")
    
    archived_page_id = None
    for page in results:
        title = page.get("title", "N/A")
        page_id = page.get("id", "N/A")
        space = page.get("space", {}).get("key", "N/A")
        
        print(f"  📄 {title}")
        print(f"     ID: {page_id} | Space: {space}")
        
        # Check ancestors to understand hierarchy
        ancestors = page.get("ancestors", [])
        if ancestors:
            ancestor_path = " → ".join([a.get("title", "?") for a in ancestors])
            print(f"     Path: {ancestor_path} → {title}")
        
        # Remember if this is the main ARCHIVED page
        if "ARCHIVED" in title and "To be deleted" in title:
            archived_page_id = page_id
        print()
else:
    print("❌ Search failed")

# ============================================================
# STEP 2: Search specifically for "ProPM Roles" 
# ============================================================
print("\n" + "=" * 70)
print("STEP 2: Searching for 'ProPM Roles & Responsibilities'")
print("=" * 70)

search_result = search_pages("ProPM Roles")
if search_result:
    results = search_result.get("results", [])
    print(f"Found {len(results)} matching pages:\n")
    
    target_page_id = None
    for page in results:
        title = page.get("title", "N/A")
        page_id = page.get("id", "N/A")
        space = page.get("space", {}).get("key", "N/A")
        
        print(f"  📄 {title}")
        print(f"     ID: {page_id} | Space: {space}")
        
        ancestors = page.get("ancestors", [])
        if ancestors:
            ancestor_path = " → ".join([a.get("title", "?") for a in ancestors])
            print(f"     Path: {ancestor_path} → {title}")
        
        # Check if this is under ARCHIVED
        for ancestor in ancestors:
            if "ARCHIVED" in ancestor.get("title", ""):
                target_page_id = page_id
                print(f"     ✅ This is under ARCHIVED!")
        print()
else:
    print("❌ Search failed")

# ============================================================
# STEP 3: If we found the target, explore its structure
# ============================================================
if target_page_id:
    print("\n" + "=" * 70)
    print(f"STEP 3: Exploring target page (ID: {target_page_id})")
    print("=" * 70)
    
    page_data = get_page_with_attachments(target_page_id)
    if page_data:
        print(f"\n📄 Title: {page_data.get('title')}")
        print(f"🔑 ID: {page_data.get('id')}")
        print(f"📁 Space: {page_data.get('space', {}).get('name')}")
        print(f"📋 Version: {page_data.get('version', {}).get('number')}")
        
        # Ancestors (parent pages)
        ancestors = page_data.get('ancestors', [])
        if ancestors:
            print(f"\n📂 Page hierarchy:")
            for i, ancestor in enumerate(ancestors):
                print(f"   {'  ' * i}└─ {ancestor.get('title')} (ID: {ancestor.get('id')})")
            print(f"   {'  ' * len(ancestors)}└─ {page_data.get('title')} ← (current)")
        
        # Attachments
        print("\n" + "-" * 50)
        print("📎 ATTACHMENTS:")
        print("-" * 50)
        attachments_data = get_page_attachments(target_page_id)
        if attachments_data:
            attachments = attachments_data.get("results", [])
            if attachments:
                for att in attachments:
                    print(f"  • {att.get('title')}")
                    print(f"    Type: {att.get('metadata', {}).get('mediaType', 'unknown')}")
                    print(f"    Size: {att.get('extensions', {}).get('fileSize', 'N/A')} bytes")
                    print(f"    Download: {confluence_url}{att.get('_links', {}).get('download', '')}")
            else:
                print("  No attachments found")
        
        # Content preview
        print("\n" + "-" * 50)
        print("📝 CONTENT PREVIEW (raw HTML):")
        print("-" * 50)
        content = page_data.get("body", {}).get("storage", {}).get("value", "")
        # Show first 2000 chars to see structure including image tags
        print(content[:2000])
        if len(content) > 2000:
            print(f"\n... [truncated, total length: {len(content)} chars]")
        
        # Look for images in content
        print("\n" + "-" * 50)
        print("🖼️ IMAGES REFERENCED IN CONTENT:")
        print("-" * 50)
        import re
        # Find ac:image tags (Confluence macro)
        ac_images = re.findall(r'<ac:image[^>]*>.*?</ac:image>', content, re.DOTALL)
        # Find regular img tags
        img_tags = re.findall(r'<img[^>]+>', content)
        # Find ri:attachment references
        ri_attachments = re.findall(r'<ri:attachment ri:filename="([^"]+)"', content)
        
        if ac_images:
            print(f"  Found {len(ac_images)} Confluence image macros")
            for img in ac_images[:5]:
                print(f"    {img[:200]}")
        if img_tags:
            print(f"  Found {len(img_tags)} <img> tags")
            for img in img_tags[:5]:
                print(f"    {img[:200]}")
        if ri_attachments:
            print(f"  Found {len(ri_attachments)} attachment references:")
            for att_name in ri_attachments:
                print(f"    • {att_name}")
        
        if not (ac_images or img_tags or ri_attachments):
            print("  No embedded images found in content")

        # Child pages
        print("\n" + "-" * 50)
        print("📁 CHILD PAGES:")
        print("-" * 50)
        children_result = get_page_children(target_page_id)
        if children_result:
            children = children_result.get("results", [])
            if children:
                for child in children:
                    print(f"  • {child.get('title')} (ID: {child.get('id')})")
            else:
                print("  No child pages")
else:
    print("\n⚠️ Target page not found. Let's try listing all pages in CIPPMOPF space...")
    
    # List pages in CIPPMOPF that might contain ARCHIVED
    url = f"{confluence_url}/rest/api/content/search"
    params = {
        "cql": 'space = "CIPPMOPF" AND title ~ "ARCHIVED"',
        "limit": 50,
        "expand": "ancestors"
    }
    response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30, verify=False)
    if response.ok:
        results = response.json().get("results", [])
        print(f"\nFound {len(results)} ARCHIVED-related pages in CIPPMOPF:")
        for page in results:
            print(f"  📄 {page.get('title')} (ID: {page.get('id')})")

print("\n" + "=" * 70)
print("✅ Exploration complete!")
print("=" * 70)
