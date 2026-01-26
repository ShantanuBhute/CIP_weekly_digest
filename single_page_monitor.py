"""
Single Page Monitor - ProPM Roles & Responsibilities
Monitors ONE specific page for changes using text comparison
Only re-processes if actual changes detected
"""

import os
import json
import hashlib
import requests
from datetime import datetime
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from azure.storage.blob import BlobServiceClient

load_dotenv()

# Target page configuration
PAGE_ID = "164168599"
PAGE_TITLE = "ProPM Roles & Responsibilities"
SPACE_KEY = "CIPPMOPF"

# Confluence API configuration
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
AUTH = HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)

# Azure Blob Storage
STORAGE_CONNECTION_STRING = os.getenv("BLOB_STORAGE_CONNECTION_STRING")
CONTAINER_STATE = "confluence-state"

# Disable SSL warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_blob_service_client():
    """Get Azure Blob Storage client with SSL disabled"""
    return BlobServiceClient.from_connection_string(
        STORAGE_CONNECTION_STRING,
        connection_verify=False
    )


def extract_raw_text(page_id):
    """
    Extract raw text content from page using Confluence API
    Returns: raw text string for comparison
    """
    print(f"\n[EXTRACT] Extracting raw content from page {page_id}...")
    
    # Get page content from Confluence API
    url = f"{CONFLUENCE_URL}/rest/api/content/{page_id}"
    params = {
        "expand": "body.storage,version,space"
    }
    
    response = requests.get(url, auth=AUTH, params=params, verify=False)
    response.raise_for_status()
    page_data = response.json()
    
    title = page_data.get('title', 'Untitled')
    version = page_data.get('version', {}).get('number', 1)
    html_content = page_data.get('body', {}).get('storage', {}).get('value', '')
    
    # Simple HTML to text conversion for comparison
    import re
    from html import unescape
    
    # Remove HTML tags but keep structure markers
    text = html_content
    
    # Replace headers with markers
    text = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n[HEADING] \1\n', text, flags=re.DOTALL)
    
    # Replace list items
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'\n- \1', text, flags=re.DOTALL)
    
    # Replace table cells
    text = re.sub(r'<t[hd][^>]*>(.*?)</t[hd]>', r' | \1 ', text, flags=re.DOTALL)
    text = re.sub(r'</tr>', r'\n', text)
    
    # Replace images with markers - handle both attachments and external URLs
    text = re.sub(r'<ac:image[^>]*>.*?<ri:attachment ri:filename="([^"]+)"[^/]*/?>.*?</ac:image>', r'\n[IMAGE_ATTACHMENT: \1]\n', text, flags=re.DOTALL)
    text = re.sub(r'<ac:image[^>]*ac:alt="([^"]*)"[^>]*>.*?<ri:url ri:value="([^"]+)"[^/]*/?>.*?</ac:image>', r'\n[IMAGE_EXTERNAL: \1 | URL: \2]\n', text, flags=re.DOTALL)
    text = re.sub(r'<ac:image[^>]*>.*?<ri:url ri:value="([^"]+)"[^/]*/?>.*?</ac:image>', r'\n[IMAGE_EXTERNAL: \1]\n', text, flags=re.DOTALL)
    text = re.sub(r'<ac:image[^>]*>.*?</ac:image>', r'\n[IMAGE]\n', text, flags=re.DOTALL)
    
    # Remove remaining HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Clean up whitespace
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n\s+', '\n', text)
    text = text.strip()
    
    # Build final raw text
    raw_text = f"TITLE: {title}\nVERSION: {version}\n\n{text}"
    
    # Calculate hash for quick comparison
    content_hash = hashlib.sha256(raw_text.encode()).hexdigest()
    
    print(f"   Title: {title}")
    print(f"   Version: {version}")
    print(f"   Content length: {len(raw_text)} chars")
    print(f"   Hash: {content_hash[:16]}...")
    
    return {
        'raw_text': raw_text,
        'content_hash': content_hash,
        'extracted_at': datetime.utcnow().isoformat(),
        'page_id': page_id,
        'confluence_version': version
    }


def load_previous_version(page_id):
    """
    Load the last processed version from blob storage
    Returns: version data or None if first run
    """
    try:
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(CONTAINER_STATE)
        
        blob_name = f"page_{page_id}_raw_version.json"
        blob_client = container_client.get_blob_client(blob_name)
        
        content = blob_client.download_blob().readall()
        version_data = json.loads(content)
        
        print(f"[OK] Found previous version: v{version_data['version_number']}")
        print(f"   Last checked: {version_data['extracted_at']}")
        print(f"   Content hash: {version_data['content_hash'][:16]}...")
        
        return version_data
    
    except Exception as e:
        print(f"[WARN] No previous version found (first run)")
        return None


def save_current_version(page_id, raw_data, version_number):
    """
    Save current version to blob storage
    """
    try:
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(CONTAINER_STATE)
        
        # Ensure container exists
        try:
            container_client.create_container()
        except:
            pass
        
        # Prepare version data
        version_data = {
            'page_id': page_id,
            'version_number': version_number,
            'content_hash': raw_data['content_hash'],
            'raw_text': raw_data['raw_text'],
            'extracted_at': raw_data['extracted_at'],
            'confluence_version': raw_data['confluence_version']
        }
        
        # Save current version
        blob_name = f"page_{page_id}_raw_version.json"
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(
            json.dumps(version_data, indent=2),
            overwrite=True
        )
        
        # Also save to history
        history_name = f"page_{page_id}_history/v{version_number}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        history_client = container_client.get_blob_client(history_name)
        history_client.upload_blob(
            json.dumps(version_data, indent=2),
            overwrite=True
        )
        
        print(f"[OK] Saved version v{version_number} to blob storage")
        return True
    
    except Exception as e:
        print(f"[ERROR] Failed to save version: {e}")
        return False


def detect_changes_optimized(page_id):
    """
    Optimized change detection using text comparison
    
    Returns:
        {
            'has_changes': bool,
            'version_number': int,
            'previous_version': int or None,
            'change_summary': str,
            'needs_reprocessing': bool
        }
    """
    print("\n" + "="*70)
    print(f"CHANGE DETECTION: Page {page_id}")
    print("="*70)
    
    # Step 1: Extract current raw text
    current_data = extract_raw_text(page_id)
    
    # Step 2: Load previous version
    previous_version = load_previous_version(page_id)
    
    # Step 3: Compare
    if previous_version is None:
        # First run - no previous version
        print("\n[NEW] FIRST RUN - No previous version found")
        version_number = 1
        has_changes = True
        change_summary = "Initial extraction"
    
    elif current_data['content_hash'] == previous_version['content_hash']:
        # No changes - content identical
        print("\n[OK] NO CHANGES DETECTED")
        print(f"   Content hash matches: {current_data['content_hash'][:16]}...")
        print(f"   Keeping version: v{previous_version['version_number']}")
        
        return {
            'has_changes': False,
            'version_number': previous_version['version_number'],
            'previous_version': previous_version['version_number'],
            'change_summary': 'No changes detected',
            'needs_reprocessing': False
        }
    
    else:
        # Changes detected
        print("\n[CHANGED] CHANGES DETECTED")
        print(f"   Previous hash: {previous_version['content_hash'][:16]}...")
        print(f"   Current hash:  {current_data['content_hash'][:16]}...")
        
        version_number = previous_version['version_number'] + 1
        has_changes = True
        
        # Detailed diff - identify what actually changed
        prev_lines = previous_version['raw_text'].split('\n')
        curr_lines = current_data['raw_text'].split('\n')
        
        prev_set = set(prev_lines)
        curr_set = set(curr_lines)
        
        added_lines = curr_set - prev_set
        removed_lines = prev_set - curr_set
        
        # Categorize changes
        changes = {
            'images_added': [],
            'images_removed': [],
            'text_added': [],
            'text_removed': [],
            'headings_added': [],
            'headings_removed': []
        }
        
        for line in added_lines:
            line = line.strip()
            if '[IMAGE_EXTERNAL:' in line or '[IMAGE_ATTACHMENT:' in line or '[IMAGE:' in line:
                changes['images_added'].append(line)
            elif '[HEADING]' in line:
                changes['headings_added'].append(line.replace('[HEADING]', '').strip())
            elif line and len(line) > 10:
                changes['text_added'].append(line[:100])
        
        for line in removed_lines:
            line = line.strip()
            if '[IMAGE_EXTERNAL:' in line or '[IMAGE_ATTACHMENT:' in line or '[IMAGE:' in line:
                changes['images_removed'].append(line)
            elif '[HEADING]' in line:
                changes['headings_removed'].append(line.replace('[HEADING]', '').strip())
            elif line and len(line) > 10:
                changes['text_removed'].append(line[:100])
        
        added = len(added_lines)
        removed = len(removed_lines)
        
        # Build meaningful change summary
        summary_parts = []
        
        if changes['images_added']:
            for img in changes['images_added']:
                # Extract image info
                if 'IMAGE_EXTERNAL:' in img:
                    img_desc = img.replace('[IMAGE_EXTERNAL:', '').replace(']', '').strip()
                    summary_parts.append(f"NEW IMAGE ADDED: {img_desc}")
                elif 'IMAGE_ATTACHMENT:' in img:
                    img_desc = img.replace('[IMAGE_ATTACHMENT:', '').replace(']', '').strip()
                    summary_parts.append(f"NEW IMAGE ADDED: {img_desc}")
        
        if changes['images_removed']:
            for img in changes['images_removed']:
                summary_parts.append(f"IMAGE REMOVED: {img}")
        
        if changes['headings_added']:
            for h in changes['headings_added'][:3]:  # Limit to 3
                summary_parts.append(f"NEW SECTION: {h}")
        
        if changes['headings_removed']:
            for h in changes['headings_removed'][:3]:
                summary_parts.append(f"SECTION REMOVED: {h}")
        
        if changes['text_added']:
            # Include sample of actual text added
            for txt in changes['text_added'][:3]:
                summary_parts.append(f"NEW TEXT: \"{txt[:80]}...\"")
        
        if changes['text_removed']:
            for txt in changes['text_removed'][:2]:
                summary_parts.append(f"TEXT REMOVED: \"{txt[:60]}...\"")
        
        if summary_parts:
            change_summary = " | ".join(summary_parts)
        else:
            change_summary = f"Minor content changes: {added} additions, {removed} removals"
        
        print(f"\\n   CHANGE DETAILS:")
        for part in summary_parts[:5]:
            print(f"     • {part}")
        print(f"   Incrementing version: v{previous_version['version_number']} → v{version_number}")
    
    # Step 4: Save current version (include detailed changes)
    current_data['changes'] = changes if 'changes' in dir() else None
    save_current_version(page_id, current_data, version_number)
    
    result = {
        'has_changes': has_changes,
        'version_number': version_number,
        'previous_version': previous_version['version_number'] if previous_version else None,
        'change_summary': change_summary,
        'needs_reprocessing': has_changes,
        'current_data': current_data
    }
    
    print("\n" + "="*70)
    print(f"RESULT: Version v{version_number} | Changes: {has_changes} | Reprocess: {has_changes}")
    print("="*70 + "\n")
    
    return result


if __name__ == "__main__":
    result = detect_changes_optimized(PAGE_ID)
    
    # Save result summary
    os.makedirs("data", exist_ok=True)
    output_file = f"data/change_detection_{PAGE_ID}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(output_file, 'w') as f:
        # Don't save raw_text to keep file small
        summary = {k: v for k, v in result.items() if k != 'current_data'}
        json.dump(summary, f, indent=2)
    
    print(f"✅ Detection summary saved: {output_file}")
    
    if result['needs_reprocessing']:
        print(f"\n⚠️  NEXT STEP: Run full pipeline to reprocess page")
        print(f"   Command: python run_single_page_pipeline.py")
    else:
        print(f"\n✅ No reprocessing needed - content unchanged")
