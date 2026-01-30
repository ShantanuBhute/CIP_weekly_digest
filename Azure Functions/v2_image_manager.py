"""
V2 Image Manager - Optimized Image Downloading with Hash-Based Caching
Only downloads images that are new or changed.

Key Optimizations:
1. Check blob storage for existing image by hash BEFORE downloading
2. Skip download if image already exists in storage
3. Track image hashes for GPT-4o description caching
"""

import os
import re
import json
import hashlib
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from v2_storage_manager import V2StorageManager, get_v2_storage_manager

load_dotenv()

# Confluence configuration
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
AUTH = HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)

# Disable SSL warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class V2ImageManager:
    """
    Manages image downloading with intelligent caching.
    Only downloads images that are new or have changed.
    """
    
    def __init__(self, storage_manager: V2StorageManager = None):
        self.storage = storage_manager or get_v2_storage_manager()
        self.download_stats = {
            'downloaded': 0,
            'skipped_cached': 0,
            'failed': 0,
            'bytes_downloaded': 0,
            'bytes_saved': 0
        }
    
    def get_attachment_info(self, page_id: str) -> Dict[str, Dict]:
        """
        Get all attachments for a page with their metadata.
        Returns dict of filename -> attachment info including version hash.
        """
        url = f"{CONFLUENCE_URL}/rest/api/content/{page_id}/child/attachment"
        params = {"expand": "version,metadata", "limit": 100}
        
        try:
            response = requests.get(url, auth=AUTH, params=params, timeout=30, verify=False)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"   ❌ Failed to get attachments: {e}")
            return {}
        
        attachments = {}
        for att in data.get('results', []):
            filename = att.get('title', '')
            version = att.get('version', {}).get('number', 1)
            file_size = att.get('extensions', {}).get('fileSize', 0)
            
            # Create a version hash based on attachment version and size
            # This changes when the image is updated in Confluence
            version_string = f"{filename}:{version}:{file_size}"
            version_hash = hashlib.md5(version_string.encode()).hexdigest()
            
            attachments[filename] = {
                'id': att.get('id'),
                'title': filename,
                'version': version,
                'file_size': file_size,
                'media_type': att.get('metadata', {}).get('mediaType', 'unknown'),
                'download_link': att.get('_links', {}).get('download', ''),
                'version_hash': version_hash
            }
        
        return attachments
    
    def check_image_in_cache(
        self,
        space_key: str,
        page_id: str,
        page_title: str,
        filename: str,
        version_hash: str
    ) -> Optional[Tuple[str, str]]:
        """
        Check if image with this version exists in blob storage.
        
        Returns:
            (blob_url, image_hash) if exists, None otherwise
        """
        # Check if we have this exact version cached
        base_path = self.storage.get_page_base_path(space_key, page_id, page_title)
        
        # List images in the page's image folder
        container_client = self.storage.blob_service.get_container_client("confluence-content")
        prefix = f"{base_path}/images/"
        
        try:
            for blob in container_client.list_blobs(name_starts_with=prefix):
                blob_client = container_client.get_blob_client(blob.name)
                props = blob_client.get_blob_properties()
                metadata = props.metadata or {}
                
                # Check if this blob is for the same original file and version
                stored_filename = metadata.get('original_filename', '')
                stored_version = metadata.get('version_hash', '')
                
                if stored_filename == filename and stored_version == version_hash:
                    image_hash = metadata.get('image_hash', '')
                    return (blob_client.url, image_hash)
        except Exception:
            pass
        
        return None
    
    def download_attachment(
        self,
        download_link: str,
        local_path: str
    ) -> Tuple[bool, int]:
        """
        Download attachment from Confluence.
        
        Returns:
            (success: bool, bytes_downloaded: int)
        """
        url = f"{CONFLUENCE_URL}{download_link}"
        
        try:
            response = requests.get(url, auth=AUTH, timeout=60, verify=False)
            if response.ok:
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                return (True, len(response.content))
        except Exception as e:
            print(f"      ❌ Download failed: {e}")
        
        return (False, 0)
    
    def download_external_image(
        self,
        url: str,
        local_path: str
    ) -> Tuple[bool, int]:
        """
        Download image from external URL.
        
        Returns:
            (success: bool, bytes_downloaded: int)
        """
        try:
            response = requests.get(url, timeout=30, verify=False)
            if response.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                return (True, len(response.content))
        except Exception as e:
            print(f"      ❌ External download failed: {e}")
        
        return (False, 0)
    
    def process_page_images(
        self,
        page_id: str,
        space_key: str,
        page_title: str,
        content_blocks: List[Dict],
        local_folder: Path
    ) -> Dict[str, Dict]:
        """
        Process all images in content blocks with smart caching.
        
        1. Check if image already exists in blob storage
        2. Only download if new or changed
        3. Upload to blob with content-addressing
        4. Return image info with hashes for description caching
        
        Returns:
            Dict[filename] -> {
                'blob_url': str,
                'image_hash': str,
                'downloaded': bool,
                'local_path': str (if downloaded)
            }
        """
        print(f"\n   🖼️ Processing images for: {page_title}")
        
        # Get attachment info from Confluence
        attachments = self.get_attachment_info(page_id)
        print(f"      Found {len(attachments)} attachments")
        
        # Create local images folder
        images_folder = local_folder / "images"
        images_folder.mkdir(parents=True, exist_ok=True)
        
        processed_images = {}
        
        for block in content_blocks:
            if block['type'] != 'image':
                continue
            
            source = block.get('source', '')
            filename = block.get('filename', f"image_{block.get('index', 0)}")
            
            # Handle attachment images
            if source == 'attachment' and filename in attachments:
                att_info = attachments[filename]
                version_hash = att_info['version_hash']
                
                print(f"\n      📎 {filename} (v{att_info['version']})")
                
                # Check blob cache first
                cached = self.check_image_in_cache(
                    space_key, page_id, page_title, filename, version_hash
                )
                
                if cached:
                    blob_url, image_hash = cached
                    print(f"         ♻️ CACHED (hash={image_hash[:8]})")
                    self.download_stats['skipped_cached'] += 1
                    self.download_stats['bytes_saved'] += att_info.get('file_size', 0)
                    
                    processed_images[filename] = {
                        'blob_url': blob_url,
                        'image_hash': image_hash,
                        'downloaded': False,
                        'from_cache': True
                    }
                    continue
                
                # Need to download
                local_path = images_folder / f"{block.get('index', 0):03d}_{filename}"
                success, bytes_downloaded = self.download_attachment(
                    att_info['download_link'],
                    str(local_path)
                )
                
                if success:
                    self.download_stats['downloaded'] += 1
                    self.download_stats['bytes_downloaded'] += bytes_downloaded
                    
                    # Upload to blob with deduplication
                    uploaded, blob_url, image_hash = self.storage.upload_image_deduplicated(
                        space_key, page_id, page_title,
                        str(local_path), filename
                    )
                    
                    # Store version hash in blob metadata for future cache hits
                    if uploaded:
                        blob_path = f"{self.storage.get_page_base_path(space_key, page_id, page_title)}/images/{image_hash[:8]}_{self.storage.sanitize_name(Path(filename).stem)}{Path(filename).suffix}"
                        blob_client = self.storage.blob_service.get_blob_client("confluence-content", blob_path)
                        try:
                            blob_client.set_blob_metadata({
                                'image_hash': image_hash,
                                'original_filename': filename,
                                'version_hash': version_hash
                            })
                        except Exception:
                            pass
                    
                    processed_images[filename] = {
                        'blob_url': blob_url,
                        'image_hash': image_hash,
                        'downloaded': True,
                        'local_path': str(local_path),
                        'from_cache': False
                    }
                else:
                    self.download_stats['failed'] += 1
            
            # Handle external URL images
            elif source == 'external_url':
                external_url = block.get('external_url', '')
                if not external_url:
                    continue
                
                print(f"\n      🌐 {filename[:40]}...")
                
                # For external URLs, use URL hash as version
                url_hash = hashlib.md5(external_url.encode()).hexdigest()
                
                # Check cache
                cached = self.check_image_in_cache(
                    space_key, page_id, page_title, filename, url_hash
                )
                
                if cached:
                    blob_url, image_hash = cached
                    print(f"         ♻️ CACHED (hash={image_hash[:8]})")
                    self.download_stats['skipped_cached'] += 1
                    
                    processed_images[filename] = {
                        'blob_url': blob_url,
                        'image_hash': image_hash,
                        'downloaded': False,
                        'from_cache': True
                    }
                    continue
                
                # Download external image
                local_path = images_folder / f"{block.get('index', 0):03d}_{filename}"
                success, bytes_downloaded = self.download_external_image(
                    external_url, str(local_path)
                )
                
                if success:
                    self.download_stats['downloaded'] += 1
                    self.download_stats['bytes_downloaded'] += bytes_downloaded
                    
                    # Upload with deduplication
                    uploaded, blob_url, image_hash = self.storage.upload_image_deduplicated(
                        space_key, page_id, page_title,
                        str(local_path), filename
                    )
                    
                    # Store URL hash for caching
                    if uploaded:
                        blob_path = f"{self.storage.get_page_base_path(space_key, page_id, page_title)}/images/{image_hash[:8]}_{self.storage.sanitize_name(Path(filename).stem)}{Path(filename).suffix}"
                        blob_client = self.storage.blob_service.get_blob_client("confluence-content", blob_path)
                        try:
                            blob_client.set_blob_metadata({
                                'image_hash': image_hash,
                                'original_filename': filename,
                                'version_hash': url_hash
                            })
                        except Exception:
                            pass
                    
                    processed_images[filename] = {
                        'blob_url': blob_url,
                        'image_hash': image_hash,
                        'downloaded': True,
                        'local_path': str(local_path),
                        'from_cache': False
                    }
                else:
                    self.download_stats['failed'] += 1
        
        # Print stats
        print(f"\n   📊 Image Processing Stats:")
        print(f"      • Downloaded: {self.download_stats['downloaded']} ({self.download_stats['bytes_downloaded']:,} bytes)")
        print(f"      • From cache: {self.download_stats['skipped_cached']} (saved ~{self.download_stats['bytes_saved']:,} bytes)")
        print(f"      • Failed: {self.download_stats['failed']}")
        
        return processed_images


def get_v2_image_manager(storage_manager: V2StorageManager = None) -> V2ImageManager:
    """Factory function to get V2 image manager"""
    return V2ImageManager(storage_manager)


# Test
if __name__ == "__main__":
    print("=" * 70)
    print("V2 IMAGE MANAGER TEST")
    print("=" * 70)
    
    manager = get_v2_image_manager()
    
    # Test attachment info
    page_id = "164168599"
    attachments = manager.get_attachment_info(page_id)
    
    print(f"\nFound {len(attachments)} attachments:")
    for name, info in attachments.items():
        print(f"  • {name} (v{info['version']}, {info['file_size']:,} bytes)")
    
    print("\n✅ V2 Image Manager initialized successfully")
