"""
Confluence Explorer - Detailed exploration of ARCHIVED page and its sub-pages
"""

import os
import json
import sys
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import urllib3
import re

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

confluence_url = os.getenv("CONFLUENCE_URL")
api_token = os.getenv("CONFLUENCE_API_TOKEN")
email = os.getenv("CONFLUENCE_EMAIL")

headers = {"Accept": "application/json"}
auth = HTTPBasicAuth(email, api_token) if email else HTTPBasicAuth("", api_token)

# The ARCHIVED - To be deleted page ID we found
ARCHIVED_PAGE_ID = "304287253"


def get_page_children(page_id, limit=100):
    """Get child pages of a given page"""
    url = f"{confluence_url}/rest/api/content/{page_id}/child/page"
    params = {"limit": limit, "expand": "version,space,children.page"}
    response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30, verify=False)
    return response.json() if response.ok else None


def get_page_details(page_id):
    """Get full page details including body and attachments"""
    url = f"{confluence_url}/rest/api/content/{page_id}"
    params = {
        "expand": "body.storage,body.view,version,space,ancestors,children.page,children.attachment,metadata.labels"
    }
    response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30, verify=False)
    return response.json() if response.ok else None


def get_page_attachments(page_id):
    """Get all attachments for a page"""
    url = f"{confluence_url}/rest/api/content/{page_id}/child/attachment"
    params = {"expand": "version,metadata", "limit": 100}
    response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30, verify=False)
    return response.json() if response.ok else None


def extract_images_from_content(html_content):
    """Extract all image references from Confluence HTML content"""
    images = []
    
    # Pattern 1: ac:image with ri:attachment (attached images)
    pattern1 = re.compile(r'<ac:image[^>]*>.*?<ri:attachment ri:filename="([^"]+)"[^/]*/?>.*?</ac:image>', re.DOTALL)
    for match in pattern1.finditer(html_content):
        images.append({"type": "attachment", "filename": match.group(1)})
    
    # Pattern 2: ac:image with ri:url (external images)
    pattern2 = re.compile(r'<ac:image[^>]*>.*?<ri:url ri:value="([^"]+)"[^/]*/?>.*?</ac:image>', re.DOTALL)
    for match in pattern2.finditer(html_content):
        images.append({"type": "external_url", "url": match.group(1)})
    
    # Pattern 3: Regular img tags with src
    pattern3 = re.compile(r'<img[^>]+src="([^"]+)"[^>]*>', re.IGNORECASE)
    for match in pattern3.finditer(html_content):
        images.append({"type": "img_tag", "src": match.group(1)})
    
    # Pattern 4: ac:emoticon (emoji/icons)
    pattern4 = re.compile(r'<ac:emoticon ac:name="([^"]+)"[^/]*/>', re.IGNORECASE)
    for match in pattern4.finditer(html_content):
        images.append({"type": "emoticon", "name": match.group(1)})
    
    return images


def print_page_summary(page_data, indent=0):
    """Print a summary of a page"""
    prefix = "  " * indent
    title = page_data.get('title', 'N/A')
    page_id = page_data.get('id', 'N/A')
    version = page_data.get('version', {}).get('number', 'N/A')
    
    print(f"{prefix}📄 {title}")
    print(f"{prefix}   ID: {page_id} | Version: {version}")
    
    # Count attachments if available
    attachments = page_data.get('children', {}).get('attachment', {}).get('results', [])
    if attachments:
        print(f"{prefix}   📎 {len(attachments)} attachment(s)")
    
    return page_id


def explore_page_tree(page_id, indent=0, max_depth=3):
    """Recursively explore page tree"""
    if indent > max_depth:
        return []
    
    pages_found = []
    children = get_page_children(page_id)
    
    if children:
        for child in children.get('results', []):
            child_id = print_page_summary(child, indent)
            pages_found.append({
                'id': child_id,
                'title': child.get('title'),
                'version': child.get('version', {}).get('number')
            })
            
            # Recurse into sub-children
            sub_children = child.get('children', {}).get('page', {}).get('results', [])
            if sub_children:
                pages_found.extend(explore_page_tree(child_id, indent + 1, max_depth))
    
    return pages_found


# ============================================================
# STEP 1: List all children of ARCHIVED page
# ============================================================
print("=" * 70)
print(f"Exploring children of 'ARCHIVED - To be deleted' (ID: {ARCHIVED_PAGE_ID})")
print("=" * 70)

archived_page = get_page_details(ARCHIVED_PAGE_ID)
if archived_page:
    print(f"\n📁 {archived_page.get('title')}")
    print(f"   Space: {archived_page.get('space', {}).get('name')}")
    print(f"   Version: {archived_page.get('version', {}).get('number')}")
    print()

print("\n📂 Child pages (recursive):")
print("-" * 50)
all_pages = explore_page_tree(ARCHIVED_PAGE_ID)

# ============================================================
# STEP 2: Find and analyze ProPM Roles & Responsibilities
# ============================================================
print("\n" + "=" * 70)
print("Searching for 'ProPM Roles & Responsibilities' in children...")
print("=" * 70)

target_page = None
for page in all_pages:
    if "ProPM" in page['title'] or "Roles" in page['title']:
        target_page = page
        print(f"\n✅ Found: {page['title']} (ID: {page['id']})")
        break

if not target_page:
    # Search by CQL in CIPPMOPF space
    print("\nSearching via CQL...")
    url = f"{confluence_url}/rest/api/content/search"
    params = {
        "cql": f'ancestor = {ARCHIVED_PAGE_ID} AND type = page',
        "limit": 50,
        "expand": "version"
    }
    response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30, verify=False)
    if response.ok:
        results = response.json().get("results", [])
        print(f"Found {len(results)} pages under ARCHIVED:")
        for page in results:
            print(f"  • {page.get('title')} (ID: {page.get('id')})")
            if "ProPM" in page.get('title', '') or "Role" in page.get('title', ''):
                target_page = {'id': page.get('id'), 'title': page.get('title')}

# ============================================================
# STEP 3: Deep dive into target page (or first available)
# ============================================================
if target_page:
    page_id = target_page['id']
else:
    # Use first child page for demo
    page_id = all_pages[0]['id'] if all_pages else None

if page_id:
    print("\n" + "=" * 70)
    print(f"DETAILED ANALYSIS OF PAGE (ID: {page_id})")
    print("=" * 70)
    
    page_data = get_page_details(page_id)
    if page_data:
        print(f"\n📄 Title: {page_data.get('title')}")
        print(f"🔑 Page ID: {page_data.get('id')}")
        print(f"📁 Space: {page_data.get('space', {}).get('key')} - {page_data.get('space', {}).get('name')}")
        print(f"📋 Version: {page_data.get('version', {}).get('number')}")
        print(f"📅 Last Modified: {page_data.get('version', {}).get('when')}")
        print(f"👤 Modified By: {page_data.get('version', {}).get('by', {}).get('displayName', 'N/A')}")
        
        # URL
        web_link = page_data.get('_links', {}).get('webui', '')
        if web_link:
            print(f"🔗 URL: {confluence_url}{web_link}")
        
        # Labels
        labels = page_data.get('metadata', {}).get('labels', {}).get('results', [])
        if labels:
            label_names = [l.get('name') for l in labels]
            print(f"🏷️ Labels: {', '.join(label_names)}")
        
        # Attachments
        print("\n" + "-" * 50)
        print("📎 ATTACHMENTS:")
        print("-" * 50)
        attachments = get_page_attachments(page_id)
        if attachments:
            att_list = attachments.get('results', [])
            if att_list:
                for att in att_list:
                    media_type = att.get('metadata', {}).get('mediaType', 'unknown')
                    file_size = att.get('extensions', {}).get('fileSize', 0)
                    download_link = att.get('_links', {}).get('download', '')
                    
                    # Determine if it's an image
                    is_image = media_type.startswith('image/')
                    icon = "🖼️" if is_image else "📄"
                    
                    print(f"  {icon} {att.get('title')}")
                    print(f"     Type: {media_type}")
                    print(f"     Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
                    print(f"     Download: {confluence_url}{download_link}")
                    print()
            else:
                print("  No attachments found")
        
        # Content analysis
        print("-" * 50)
        print("📝 CONTENT ANALYSIS:")
        print("-" * 50)
        
        content = page_data.get('body', {}).get('storage', {}).get('value', '')
        
        print(f"  Total HTML length: {len(content):,} characters")
        
        # Extract images
        images = extract_images_from_content(content)
        print(f"  Images/media found in content: {len(images)}")
        
        if images:
            print("\n  🖼️ Image references:")
            for img in images:
                if img['type'] == 'attachment':
                    print(f"     • [Attachment] {img['filename']}")
                elif img['type'] == 'external_url':
                    print(f"     • [External] {img['url'][:80]}...")
                elif img['type'] == 'img_tag':
                    print(f"     • [IMG tag] {img['src'][:80]}...")
                elif img['type'] == 'emoticon':
                    print(f"     • [Emoticon] {img['name']}")
        
        # Show raw content preview
        print("\n" + "-" * 50)
        print("📝 RAW HTML CONTENT (first 3000 chars):")
        print("-" * 50)
        print(content[:3000])
        if len(content) > 3000:
            print(f"\n... [truncated, total: {len(content):,} chars]")
        
        # Convert to plain text preview
        print("\n" + "-" * 50)
        print("📝 PLAIN TEXT PREVIEW:")
        print("-" * 50)
        # Simple HTML to text conversion
        text_content = re.sub(r'<[^>]+>', ' ', content)
        text_content = re.sub(r'\s+', ' ', text_content).strip()
        print(text_content[:2000])

print("\n" + "=" * 70)
print("✅ Exploration complete!")
print("=" * 70)
