"""
Confluence Content Extractor - Preserves text + image order for Multimodal RAG
Extracts content blocks in sequence: text → image → text → heading → image etc.
"""

import os
import json
import sys
import re
import hashlib
from datetime import datetime
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import urllib3
from html.parser import HTMLParser

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

confluence_url = os.getenv("CONFLUENCE_URL")
api_token = os.getenv("CONFLUENCE_API_TOKEN")
email = os.getenv("CONFLUENCE_EMAIL")

headers = {"Accept": "application/json"}
auth = HTTPBasicAuth(email, api_token) if email else HTTPBasicAuth("", api_token)

# Data folder setup - use /tmp for Azure Functions, local data/ for development
def get_data_folder():
    """Get the appropriate data folder based on environment
    
    Note: This function is called at runtime (not module load time) to ensure
    environment variables are properly available in Azure Functions.
    
    Detects Azure Functions via multiple environment variables since different
    versions may set different variables.
    """
    is_azure = any([
        os.getenv("AZURE_FUNCTIONS_ENVIRONMENT"),
        os.getenv("WEBSITE_INSTANCE_ID"),
        os.getenv("WEBSITE_SITE_NAME"),
        os.getenv("FUNCTIONS_WORKER_RUNTIME")
    ])
    
    if is_azure:
        # Running in Azure Functions - use /tmp
        return Path("/tmp/data")
    else:
        # Local development
        return Path("data")

def get_pages_folder():
    """Get the pages folder path - computed at runtime"""
    return get_data_folder() / "pages"

def get_images_folder():
    """Get the images folder path - computed at runtime"""
    return get_data_folder() / "images"

# Keep these for backwards compatibility but they will be computed at import time
# For reliable Azure Functions operation, use the get_*_folder() functions instead
DATA_FOLDER = get_data_folder()
PAGES_FOLDER = DATA_FOLDER / "pages"
IMAGES_FOLDER = DATA_FOLDER / "images"


class ConfluenceContentParser:
    """
    Parses Confluence storage format HTML and extracts content blocks in order.
    Maintains sequence of: text, headings, images, tables, lists etc.
    """
    
    def __init__(self, page_id, confluence_url, auth):
        self.page_id = page_id
        self.confluence_url = confluence_url
        self.auth = auth
        self.content_blocks = []
        self.current_text = ""
        
    def parse(self, html_content):
        """Parse HTML and return ordered content blocks"""
        self.content_blocks = []
        self.current_text = ""
        
        # Process the HTML sequentially
        self._parse_html(html_content)
        
        # Flush any remaining text
        self._flush_text()
        
        return self.content_blocks
    
    def _flush_text(self):
        """Save accumulated text as a block"""
        text = self.current_text.strip()
        if text:
            self.content_blocks.append({
                "type": "text",
                "content": text,
                "index": len(self.content_blocks)
            })
        self.current_text = ""
    
    def _parse_html(self, html):
        """Parse Confluence HTML preserving order"""
        
        # Split by major elements while preserving order
        # We'll use regex to find elements and process them in order
        
        # Pattern to match Confluence elements
        patterns = [
            # Headings
            (r'<h([1-6])[^>]*>(.*?)</h\1>', self._handle_heading),
            # Confluence images (ac:image)
            (r'<ac:image[^>]*>.*?<ri:attachment ri:filename="([^"]+)"[^/]*/?>.*?</ac:image>', self._handle_ac_image),
            # External images via ri:url
            (r'<ac:image[^>]*>.*?<ri:url ri:value="([^"]+)"[^/]*/?>.*?</ac:image>', self._handle_external_image),
            # Regular img tags
            (r'<img[^>]+src="([^"]+)"[^>]*>', self._handle_img_tag),
            # Tables
            (r'<table[^>]*>.*?</table>', self._handle_table),
            # Lists (ul/ol)
            (r'<(ul|ol)[^>]*>.*?</\1>', self._handle_list),
            # Paragraphs
            (r'<p[^>]*>(.*?)</p>', self._handle_paragraph),
        ]
        
        # Build a combined pattern to find all elements in order
        position = 0
        elements = []
        
        # Find all ac:image elements
        for match in re.finditer(r'<ac:image[^>]*>.*?</ac:image>', html, re.DOTALL):
            elements.append((match.start(), match.end(), 'ac_image', match.group()))
        
        # Find all headings
        for match in re.finditer(r'<h([1-6])[^>]*>(.*?)</h\1>', html, re.DOTALL | re.IGNORECASE):
            elements.append((match.start(), match.end(), 'heading', match.group(), match.group(1), match.group(2)))
        
        # Find all tables
        for match in re.finditer(r'<table[^>]*>.*?</table>', html, re.DOTALL | re.IGNORECASE):
            elements.append((match.start(), match.end(), 'table', match.group()))
        
        # Find all lists
        for match in re.finditer(r'<(ul|ol)[^>]*>(.*?)</\1>', html, re.DOTALL | re.IGNORECASE):
            elements.append((match.start(), match.end(), 'list', match.group(), match.group(1)))
        
        # Sort by position
        elements.sort(key=lambda x: x[0])
        
        # Process in order
        position = 0
        for element in elements:
            start, end = element[0], element[1]
            
            # Extract text before this element
            if start > position:
                text_before = html[position:start]
                text_clean = self._clean_html(text_before)
                if text_clean.strip():
                    self.current_text += text_clean + " "
            
            # Flush text before processing element
            self._flush_text()
            
            # Process the element
            elem_type = element[2]
            if elem_type == 'ac_image':
                self._process_ac_image(element[3])
            elif elem_type == 'heading':
                self._process_heading(element[4], element[5])
            elif elem_type == 'table':
                self._process_table(element[3])
            elif elem_type == 'list':
                self._process_list(element[3], element[4])
            
            position = end
        
        # Process remaining text
        if position < len(html):
            text_after = html[position:]
            text_clean = self._clean_html(text_after)
            if text_clean.strip():
                self.current_text += text_clean
    
    def _clean_html(self, html):
        """Remove HTML tags and clean text"""
        # Remove ac: elements (Confluence macros)
        text = re.sub(r'<ac:[^>]*>.*?</ac:[^>]*>', '', html, flags=re.DOTALL)
        text = re.sub(r'<ac:[^/]*/>', '', text)
        # Remove ri: elements
        text = re.sub(r'<ri:[^>]*>.*?</ri:[^>]*>', '', text, flags=re.DOTALL)
        text = re.sub(r'<ri:[^/]*/>', '', text)
        # Remove other tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Clean whitespace
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _process_ac_image(self, html):
        """Process Confluence ac:image element - handles attachments AND external URLs"""
        # Extract dimensions if available
        width_match = re.search(r'ac:width="(\d+)"', html)
        height_match = re.search(r'ac:height="(\d+)"', html)
        orig_width_match = re.search(r'ac:original-width="(\d+)"', html)
        orig_height_match = re.search(r'ac:original-height="(\d+)"', html)
        alt_match = re.search(r'ac:alt="([^"]*)"', html)
        
        # Check for attachment image (ri:filename)
        filename_match = re.search(r'ri:filename="([^"]+)"', html)
        if filename_match:
            filename = filename_match.group(1)
            alt_text = alt_match.group(1) if alt_match else filename
            
            self.content_blocks.append({
                "type": "image",
                "source": "attachment",
                "filename": filename,
                "alt_text": alt_text,
                "width": int(width_match.group(1)) if width_match else None,
                "height": int(height_match.group(1)) if height_match else None,
                "index": len(self.content_blocks)
            })
            return
        
        # Check for external URL image (ri:url)
        url_match = re.search(r'ri:value="([^"]+)"', html)
        if url_match:
            external_url = url_match.group(1)
            # Extract filename from URL
            import urllib.parse
            url_path = urllib.parse.urlparse(external_url).path
            filename = os.path.basename(url_path) or f"external_image_{len(self.content_blocks)}.jpg"
            alt_text = alt_match.group(1) if alt_match else filename
            
            self.content_blocks.append({
                "type": "image",
                "source": "external_url",
                "filename": filename,
                "external_url": external_url,
                "alt_text": alt_text,
                "width": int(width_match.group(1)) if width_match else (int(orig_width_match.group(1)) if orig_width_match else None),
                "height": int(height_match.group(1)) if height_match else (int(orig_height_match.group(1)) if orig_height_match else None),
                "index": len(self.content_blocks)
            })
            return
        
        # Unknown image type - log it
        print(f"   [WARN] Unknown image format in HTML")
    
    def _process_heading(self, level, content):
        """Process heading element"""
        text = self._clean_html(content)
        if text:
            self.content_blocks.append({
                "type": "heading",
                "level": int(level),
                "content": text,
                "index": len(self.content_blocks)
            })
    
    def _process_table(self, html):
        """Process table element - extract structured data"""
        rows = []
        
        # Find all rows
        for row_match in re.finditer(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE):
            row_html = row_match.group(1)
            cells = []
            
            # Find all cells (th or td)
            for cell_match in re.finditer(r'<(th|td)[^>]*>(.*?)</\1>', row_html, re.DOTALL | re.IGNORECASE):
                cell_text = self._clean_html(cell_match.group(2))
                cells.append(cell_text)
            
            if cells:
                rows.append(cells)
        
        if rows:
            self.content_blocks.append({
                "type": "table",
                "rows": rows,
                "row_count": len(rows),
                "col_count": len(rows[0]) if rows else 0,
                "index": len(self.content_blocks)
            })
    
    def _process_list(self, html, list_type):
        """Process list element"""
        items = []
        
        for item_match in re.finditer(r'<li[^>]*>(.*?)</li>', html, re.DOTALL | re.IGNORECASE):
            item_text = self._clean_html(item_match.group(1))
            if item_text:
                items.append(item_text)
        
        if items:
            self.content_blocks.append({
                "type": "list",
                "list_type": "ordered" if list_type.lower() == "ol" else "unordered",
                "items": items,
                "index": len(self.content_blocks)
            })
    
    def _handle_heading(self, match):
        pass
    
    def _handle_ac_image(self, match):
        pass
    
    def _handle_external_image(self, match):
        pass
    
    def _handle_img_tag(self, match):
        pass
    
    def _handle_table(self, match):
        pass
    
    def _handle_list(self, match):
        pass
    
    def _handle_paragraph(self, match):
        pass


def get_page_details(page_id):
    """Get full page details"""
    url = f"{confluence_url}/rest/api/content/{page_id}"
    params = {
        "expand": "body.storage,version,space,ancestors,children.attachment,metadata.labels"
    }
    response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30, verify=False)
    return response.json() if response.ok else None


def get_page_attachments(page_id):
    """Get all attachments for a page"""
    url = f"{confluence_url}/rest/api/content/{page_id}/child/attachment"
    params = {"expand": "version,metadata", "limit": 100}
    response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30, verify=False)
    return response.json() if response.ok else None


def download_attachment(download_path, local_path):
    """Download an attachment to local path"""
    url = f"{confluence_url}{download_path}"
    response = requests.get(url, auth=auth, timeout=60, verify=False)
    if response.ok:
        with open(local_path, 'wb') as f:
            f.write(response.content)
        return True
    return False


def extract_and_save_page(page_id, output_folder=None):
    """
    Extract page content with ordered blocks and download images.
    Returns structured document ready for multimodal RAG.
    """
    
    print(f"\n{'='*70}")
    print(f"Extracting page: {page_id}")
    print(f"{'='*70}")
    
    # Get page details
    page_data = get_page_details(page_id)
    if not page_data:
        print(f"❌ Failed to fetch page {page_id}")
        return None
    
    title = page_data.get('title', 'Untitled')
    space_key = page_data.get('space', {}).get('key', 'UNKNOWN')
    version = page_data.get('version', {}).get('number', 1)
    last_modified = page_data.get('version', {}).get('when', '')
    
    print(f"📄 Title: {title}")
    print(f"📁 Space: {space_key}")
    print(f"📋 Version: {version}")
    
    # Setup folders - use runtime function to ensure Azure env vars are available
    if output_folder is None:
        pages_folder = get_pages_folder()
        output_folder = pages_folder / space_key / page_id
    else:
        output_folder = Path(output_folder)
    
    output_folder.mkdir(parents=True, exist_ok=True)
    images_folder = output_folder / "images"
    images_folder.mkdir(exist_ok=True)
    
    # Get attachments
    attachments_data = get_page_attachments(page_id)
    attachments = attachments_data.get('results', []) if attachments_data else []
    
    # Build attachment lookup
    attachment_lookup = {}
    for att in attachments:
        filename = att.get('title', '')
        attachment_lookup[filename] = {
            'id': att.get('id'),
            'title': filename,
            'media_type': att.get('metadata', {}).get('mediaType', 'unknown'),
            'file_size': att.get('extensions', {}).get('fileSize', 0),
            'download_link': att.get('_links', {}).get('download', '')
        }
    
    print(f"📎 Found {len(attachments)} attachments")
    
    # Parse HTML content
    html_content = page_data.get('body', {}).get('storage', {}).get('value', '')
    
    parser = ConfluenceContentParser(page_id, confluence_url, auth)
    content_blocks = parser.parse(html_content)
    
    print(f"📝 Extracted {len(content_blocks)} content blocks")
    
    # Download images and update paths
    downloaded_images = {}
    external_images = {}
    
    for block in content_blocks:
        if block['type'] == 'image':
            # Handle attachment images
            if block.get('source') == 'attachment':
                filename = block['filename']
                if filename in attachment_lookup:
                    att_info = attachment_lookup[filename]
                    local_filename = f"{block['index']:03d}_{filename}"
                    local_path = images_folder / local_filename
                    
                    print(f"   ⬇️ Downloading attachment: {filename}")
                    if download_attachment(att_info['download_link'], local_path):
                        block['local_path'] = str(local_path.relative_to(output_folder))
                        block['media_type'] = att_info['media_type']
                        block['file_size'] = att_info['file_size']
                        downloaded_images[filename] = str(local_path)
                        print(f"      ✅ Saved: {local_filename}")
                    else:
                        print(f"      ❌ Failed to download")
            
            # Handle external URL images
            elif block.get('source') == 'external_url':
                external_url = block.get('external_url', '')
                filename = block.get('filename', f"external_{block['index']}.jpg")
                local_filename = f"{block['index']:03d}_{filename}"
                local_path = images_folder / local_filename
                
                print(f"   🌐 Downloading external: {block.get('alt_text', filename)}")
                print(f"      URL: {external_url[:60]}...")
                
                try:
                    response = requests.get(external_url, timeout=30, verify=False)
                    if response.status_code == 200:
                        with open(local_path, 'wb') as f:
                            f.write(response.content)
                        block['local_path'] = str(local_path.relative_to(output_folder))
                        block['file_size'] = len(response.content)
                        block['media_type'] = response.headers.get('content-type', 'image/jpeg').split(';')[0]
                        external_images[filename] = str(local_path)
                        print(f"      ✅ Saved: {local_filename} ({len(response.content):,} bytes)")
                    else:
                        print(f"      ❌ HTTP {response.status_code}")
                except Exception as e:
                    print(f"      ❌ Error: {e}")
    
    total_images = len(downloaded_images) + len(external_images)
    
    # Build final document structure
    document = {
        "metadata": {
            "page_id": page_id,
            "title": title,
            "space_key": space_key,
            "version": version,
            "last_modified": last_modified,
            "url": f"{confluence_url}/wiki/spaces/{space_key}/pages/{page_id}",
            "extracted_at": datetime.utcnow().isoformat() + "Z",
            "total_blocks": len(content_blocks),
            "total_images": total_images,
            "attachment_images": len(downloaded_images),
            "external_images": len(external_images),
            "attachments_count": len(attachments)
        },
        "content_blocks": content_blocks,
        "attachments": list(attachment_lookup.values()),
        "raw_html_length": len(html_content)
    }
    
    # Save document JSON
    doc_path = output_folder / "document.json"
    with open(doc_path, 'w', encoding='utf-8') as f:
        json.dump(document, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Document saved to: {doc_path}")
    
    # Also save a human-readable version
    readable_path = output_folder / "content_readable.txt"
    with open(readable_path, 'w', encoding='utf-8') as f:
        f.write(f"{'='*70}\n")
        f.write(f"TITLE: {title}\n")
        f.write(f"PAGE ID: {page_id}\n")
        f.write(f"SPACE: {space_key}\n")
        f.write(f"VERSION: {version}\n")
        f.write(f"LAST MODIFIED: {last_modified}\n")
        f.write(f"{'='*70}\n\n")
        
        for block in content_blocks:
            block_type = block['type']
            idx = block['index']
            
            if block_type == 'heading':
                level = block['level']
                f.write(f"\n{'#' * level} {block['content']}\n\n")
            
            elif block_type == 'text':
                f.write(f"{block['content']}\n\n")
            
            elif block_type == 'image':
                f.write(f"\n[IMAGE {idx}]: {block.get('filename', 'unknown')}\n")
                if block.get('alt_text'):
                    f.write(f"  Alt: {block['alt_text']}\n")
                if block.get('local_path'):
                    f.write(f"  File: {block['local_path']}\n")
                f.write("\n")
            
            elif block_type == 'list':
                list_type = block.get('list_type', 'unordered')
                for i, item in enumerate(block.get('items', []), 1):
                    prefix = f"{i}." if list_type == 'ordered' else "•"
                    f.write(f"  {prefix} {item}\n")
                f.write("\n")
            
            elif block_type == 'table':
                f.write("\n[TABLE]\n")
                for row in block.get('rows', []):
                    f.write(f"  | {' | '.join(row)} |\n")
                f.write("\n")
    
    print(f"✅ Readable version saved to: {readable_path}")
    
    return document


def main():
    """Main entry point"""
    
    # Create data folders
    DATA_FOLDER.mkdir(exist_ok=True)
    PAGES_FOLDER.mkdir(exist_ok=True)
    IMAGES_FOLDER.mkdir(exist_ok=True)
    
    print("=" * 70)
    print("CONFLUENCE CONTENT EXTRACTOR - Multimodal RAG Ready")
    print("=" * 70)
    
    # Target page: ProPM Roles & Responsibilities
    TARGET_PAGE_ID = "164168599"
    
    # Extract the page
    document = extract_and_save_page(TARGET_PAGE_ID)
    
    if document:
        print("\n" + "=" * 70)
        print("EXTRACTION SUMMARY")
        print("=" * 70)
        
        print(f"\n📄 Page: {document['metadata']['title']}")
        print(f"📦 Total content blocks: {document['metadata']['total_blocks']}")
        print(f"🖼️ Images downloaded: {document['metadata']['total_images']}")
        
        print("\n📋 Content block sequence:")
        for block in document['content_blocks']:
            idx = block['index']
            block_type = block['type'].upper()
            
            if block_type == 'HEADING':
                preview = block['content'][:50]
                print(f"   [{idx:02d}] {block_type} (H{block['level']}): {preview}")
            elif block_type == 'TEXT':
                preview = block['content'][:50] + "..." if len(block['content']) > 50 else block['content']
                print(f"   [{idx:02d}] {block_type}: {preview}")
            elif block_type == 'IMAGE':
                print(f"   [{idx:02d}] {block_type}: {block.get('filename', 'unknown')}")
            elif block_type == 'TABLE':
                print(f"   [{idx:02d}] {block_type}: {block['row_count']} rows x {block['col_count']} cols")
            elif block_type == 'LIST':
                print(f"   [{idx:02d}] {block_type} ({block['list_type']}): {len(block['items'])} items")
            else:
                print(f"   [{idx:02d}] {block_type}")
        
        print("\n" + "=" * 70)
        print("✅ Extraction complete! Ready for Azure multimodal RAG ingestion.")
        print("=" * 70)


if __name__ == "__main__":
    main()