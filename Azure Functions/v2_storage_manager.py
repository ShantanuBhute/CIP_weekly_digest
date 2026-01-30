"""
V2 Storage Manager - Optimized Blob Storage with Hash-Based Deduplication
Implements the new folder structure:

Storage Account: cipdigest2
└── confluence-content/
    └── CIPPMOPF/
        └── {PageTitle}_{PageID}/
            ├── metadata.json          ← Page info, version history
            ├── versions/
            │   ├── v1.json
            │   ├── v2.json
            │   └── ...
            ├── images/                ← Content-addressed images (deduplicated)
            │   ├── {hash}_{filename}
            │   └── ...
            └── descriptions/          ← Cached GPT-4o descriptions
                ├── {hash}.json
                └── ...

Key Optimizations:
1. MD5 hash check before uploading - skip unchanged files
2. Content-addressed images - same image = same hash = no re-upload
3. Cached descriptions by image hash - no re-describing unchanged images
"""

import os
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient, ContentSettings

load_dotenv()

# Azure Storage configuration
STORAGE_CONNECTION_STRING = os.getenv("BLOB_STORAGE_CONNECTION_STRING")
CONTAINER_CONTENT = os.getenv("BLOB_CONTAINER_CONTENT", "confluence-content")
CONTAINER_STATE = os.getenv("BLOB_CONTAINER_STATE", "confluence-state")
CONTAINER_EMAILS = os.getenv("EMAIL_CONTAINER", "confluence-emails")


class V2StorageManager:
    """
    Optimized blob storage manager with hash-based deduplication.
    Reduces unnecessary uploads by checking MD5 hashes before uploading.
    """
    
    def __init__(self, connection_string: str = None):
        self.connection_string = connection_string or STORAGE_CONNECTION_STRING
        if not self.connection_string:
            raise ValueError("BLOB_STORAGE_CONNECTION_STRING not configured")
        
        self._blob_service = None
        self._cache = {}  # In-memory cache for this session
    
    @property
    def blob_service(self) -> BlobServiceClient:
        """Lazy initialization of blob service client"""
        if self._blob_service is None:
            self._blob_service = BlobServiceClient.from_connection_string(
                self.connection_string,
                connection_verify=False  # Corporate network SSL bypass
            )
        return self._blob_service
    
    def ensure_container(self, container_name: str) -> bool:
        """Create container if it doesn't exist"""
        try:
            container_client = self.blob_service.get_container_client(container_name)
            if not container_client.exists():
                print(f"   📦 Creating container: {container_name}")
                container_client.create_container()
            return True
        except Exception as e:
            print(f"   ❌ Container error: {e}")
            return False
    
    @staticmethod
    def sanitize_name(text: str) -> str:
        """Convert text to safe filename/path component"""
        safe = re.sub(r'[^\w\s-]', '', text)
        safe = re.sub(r'[-\s]+', '_', safe)
        return safe.strip('_')[:50]  # Limit length
    
    @staticmethod
    def compute_file_hash(file_path: str) -> str:
        """Compute MD5 hash of file for deduplication"""
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()
    
    @staticmethod
    def compute_content_hash(content: bytes) -> str:
        """Compute MD5 hash of content"""
        return hashlib.md5(content).hexdigest()
    
    def get_blob_md5(self, container: str, blob_path: str) -> Optional[str]:
        """
        Get MD5 hash of existing blob (if it exists).
        Returns None if blob doesn't exist.
        """
        try:
            blob_client = self.blob_service.get_blob_client(container, blob_path)
            properties = blob_client.get_blob_properties()
            # Azure stores MD5 as base64, but we can use content_md5 or compute
            return properties.content_settings.content_md5 or None
        except Exception:
            return None  # Blob doesn't exist
    
    def blob_exists(self, container: str, blob_path: str) -> bool:
        """Check if blob exists"""
        try:
            blob_client = self.blob_service.get_blob_client(container, blob_path)
            return blob_client.exists()
        except Exception:
            return False
    
    def get_page_base_path(self, space_key: str, page_id: str, page_title: str) -> str:
        """
        Generate base path for page: CIPPMOPF/{PageTitle}_{PageID}/
        Example: CIPPMOPF/ProPM_Roles_164168599/
        """
        safe_title = self.sanitize_name(page_title)
        return f"{space_key}/{safe_title}_{page_id}"
    
    def upload_if_changed(
        self,
        container: str,
        local_path: str,
        blob_path: str,
        content_type: str = None
    ) -> Tuple[bool, str, str]:
        """
        Upload file only if it's new or changed.
        
        Returns:
            (uploaded: bool, blob_url: str, reason: str)
            uploaded=True if file was uploaded, False if skipped
        """
        self.ensure_container(container)
        
        # Compute local file hash
        local_hash = self.compute_file_hash(local_path)
        
        # Check if blob exists with same hash
        blob_client = self.blob_service.get_blob_client(container, blob_path)
        
        try:
            if blob_client.exists():
                # Get existing blob properties
                props = blob_client.get_blob_properties()
                existing_metadata = props.metadata or {}
                existing_hash = existing_metadata.get('content_md5', '')
                
                if existing_hash == local_hash:
                    return (False, blob_client.url, f"SKIPPED (unchanged, hash={local_hash[:8]})")
        except Exception:
            pass  # Blob doesn't exist, upload it
        
        # Determine content type
        if content_type is None:
            ext = Path(local_path).suffix.lower()
            content_types = {
                '.json': 'application/json',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                '.txt': 'text/plain'
            }
            content_type = content_types.get(ext, 'application/octet-stream')
        
        # Upload with hash in metadata
        with open(local_path, 'rb') as f:
            blob_client.upload_blob(
                f,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
                metadata={'content_md5': local_hash}
            )
        
        return (True, blob_client.url, f"UPLOADED (hash={local_hash[:8]})")
    
    def upload_content_if_changed(
        self,
        container: str,
        content: bytes,
        blob_path: str,
        content_type: str = 'application/json'
    ) -> Tuple[bool, str, str]:
        """
        Upload content bytes only if changed.
        
        Returns:
            (uploaded: bool, blob_url: str, reason: str)
        """
        self.ensure_container(container)
        
        content_hash = self.compute_content_hash(content)
        blob_client = self.blob_service.get_blob_client(container, blob_path)
        
        try:
            if blob_client.exists():
                props = blob_client.get_blob_properties()
                existing_metadata = props.metadata or {}
                existing_hash = existing_metadata.get('content_md5', '')
                
                if existing_hash == content_hash:
                    return (False, blob_client.url, f"SKIPPED (unchanged)")
        except Exception:
            pass
        
        blob_client.upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
            metadata={'content_md5': content_hash}
        )
        
        return (True, blob_client.url, f"UPLOADED")
    
    def get_image_by_hash(self, space_key: str, page_id: str, page_title: str, image_hash: str) -> Optional[str]:
        """
        Check if image with given hash already exists.
        Returns blob URL if found, None otherwise.
        """
        base_path = self.get_page_base_path(space_key, page_id, page_title)
        
        # List blobs in images folder matching this hash
        container_client = self.blob_service.get_container_client(CONTAINER_CONTENT)
        prefix = f"{base_path}/images/{image_hash[:8]}_"
        
        try:
            blobs = list(container_client.list_blobs(name_starts_with=prefix))
            if blobs:
                blob_client = container_client.get_blob_client(blobs[0].name)
                return blob_client.url
        except Exception:
            pass
        
        return None
    
    def get_cached_description(self, space_key: str, page_id: str, page_title: str, image_hash: str) -> Optional[Dict]:
        """
        Get cached GPT-4o description for image hash.
        Returns description dict if found, None otherwise.
        """
        base_path = self.get_page_base_path(space_key, page_id, page_title)
        blob_path = f"{base_path}/descriptions/{image_hash}.json"
        
        try:
            blob_client = self.blob_service.get_blob_client(CONTAINER_CONTENT, blob_path)
            if blob_client.exists():
                content = blob_client.download_blob().readall()
                return json.loads(content)
        except Exception:
            pass
        
        return None
    
    def save_description_cache(
        self,
        space_key: str,
        page_id: str,
        page_title: str,
        image_hash: str,
        description_data: Dict
    ) -> str:
        """
        Cache GPT-4o description by image hash.
        Returns blob URL.
        """
        base_path = self.get_page_base_path(space_key, page_id, page_title)
        blob_path = f"{base_path}/descriptions/{image_hash}.json"
        
        self.ensure_container(CONTAINER_CONTENT)
        
        content = json.dumps(description_data, indent=2, ensure_ascii=False).encode('utf-8')
        blob_client = self.blob_service.get_blob_client(CONTAINER_CONTENT, blob_path)
        
        blob_client.upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(content_type='application/json')
        )
        
        return blob_client.url
    
    def upload_page_version(
        self,
        space_key: str,
        page_id: str,
        page_title: str,
        version: int,
        document: Dict
    ) -> Tuple[bool, str]:
        """
        Upload page version document.
        Returns (uploaded, blob_url).
        """
        base_path = self.get_page_base_path(space_key, page_id, page_title)
        blob_path = f"{base_path}/versions/v{version}.json"
        
        content = json.dumps(document, indent=2, ensure_ascii=False).encode('utf-8')
        uploaded, url, reason = self.upload_content_if_changed(
            CONTAINER_CONTENT, content, blob_path
        )
        
        print(f"   📄 Version v{version}: {reason}")
        return (uploaded, url)
    
    def update_page_metadata(
        self,
        space_key: str,
        page_id: str,
        page_title: str,
        version: int,
        additional_metadata: Dict = None
    ) -> str:
        """
        Update or create page metadata.json with version history.
        """
        base_path = self.get_page_base_path(space_key, page_id, page_title)
        blob_path = f"{base_path}/metadata.json"
        
        # Try to load existing metadata
        try:
            blob_client = self.blob_service.get_blob_client(CONTAINER_CONTENT, blob_path)
            if blob_client.exists():
                content = blob_client.download_blob().readall()
                metadata = json.loads(content)
            else:
                metadata = {
                    'page_id': page_id,
                    'title': page_title,
                    'space_key': space_key,
                    'created_at': datetime.utcnow().isoformat() + 'Z',
                    'versions': []
                }
        except Exception:
            metadata = {
                'page_id': page_id,
                'title': page_title,
                'space_key': space_key,
                'created_at': datetime.utcnow().isoformat() + 'Z',
                'versions': []
            }
        
        # Add new version to history
        version_entry = {
            'version': version,
            'processed_at': datetime.utcnow().isoformat() + 'Z'
        }
        if additional_metadata:
            version_entry.update(additional_metadata)
        
        # Check if version already exists
        existing_versions = [v['version'] for v in metadata.get('versions', [])]
        if version not in existing_versions:
            metadata['versions'].append(version_entry)
        
        metadata['latest_version'] = version
        metadata['updated_at'] = datetime.utcnow().isoformat() + 'Z'
        
        # Upload metadata
        self.ensure_container(CONTAINER_CONTENT)
        content = json.dumps(metadata, indent=2, ensure_ascii=False).encode('utf-8')
        blob_client = self.blob_service.get_blob_client(CONTAINER_CONTENT, blob_path)
        blob_client.upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(content_type='application/json')
        )
        
        return blob_client.url
    
    def upload_image_deduplicated(
        self,
        space_key: str,
        page_id: str,
        page_title: str,
        local_image_path: str,
        original_filename: str
    ) -> Tuple[bool, str, str]:
        """
        Upload image with content-addressing (hash-based deduplication).
        Same image content = same hash = no re-upload.
        
        Returns:
            (uploaded: bool, blob_url: str, image_hash: str)
        """
        # Compute hash of image content
        image_hash = self.compute_file_hash(local_image_path)
        short_hash = image_hash[:8]
        
        # Create deduplicated filename: {hash}_{original_name}
        ext = Path(original_filename).suffix
        safe_name = self.sanitize_name(Path(original_filename).stem)
        dedup_filename = f"{short_hash}_{safe_name}{ext}"
        
        base_path = self.get_page_base_path(space_key, page_id, page_title)
        blob_path = f"{base_path}/images/{dedup_filename}"
        
        # Check if already exists
        blob_client = self.blob_service.get_blob_client(CONTAINER_CONTENT, blob_path)
        
        try:
            if blob_client.exists():
                print(f"      ♻️ REUSED (hash={short_hash})")
                return (False, blob_client.url, image_hash)
        except Exception:
            pass
        
        # Upload new image
        self.ensure_container(CONTAINER_CONTENT)
        
        ext_lower = ext.lower()
        content_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        content_type = content_types.get(ext_lower, 'image/png')
        
        with open(local_image_path, 'rb') as f:
            blob_client.upload_blob(
                f,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
                metadata={'image_hash': image_hash, 'original_filename': original_filename}
            )
        
        print(f"      ⬆️ UPLOADED (hash={short_hash})")
        return (True, blob_client.url, image_hash)


def get_v2_storage_manager() -> V2StorageManager:
    """Factory function to get V2 storage manager instance"""
    return V2StorageManager()


# Example usage
if __name__ == "__main__":
    print("=" * 70)
    print("V2 STORAGE MANAGER TEST")
    print("=" * 70)
    
    manager = get_v2_storage_manager()
    
    # Test container creation
    print("\n[TEST] Checking containers...")
    manager.ensure_container(CONTAINER_CONTENT)
    manager.ensure_container(CONTAINER_STATE)
    
    # Test path generation
    path = manager.get_page_base_path("CIPPMOPF", "164168599", "ProPM Roles & Responsibilities")
    print(f"\n[TEST] Generated path: {path}")
    
    print("\n✅ V2 Storage Manager initialized successfully")
