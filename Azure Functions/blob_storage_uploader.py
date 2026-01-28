"""
Azure Blob Storage Uploader for Confluence Content
Uploads document.json and images to blob storage, updates paths to blob URLs
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient, ContentSettings

# Load environment variables
load_dotenv()

# Azure Storage configuration
STORAGE_CONNECTION_STRING = os.getenv("BLOB_STORAGE_CONNECTION_STRING")
CONTAINER_MEDIA = os.getenv("BLOB_CONTAINER_MEDIA", "confluence-media")    # All images/attachments
CONTAINER_RAG = os.getenv("BLOB_CONTAINER_RAG", "confluence-rag")          # RAG-ready JSON documents
CONTAINER_STATE = os.getenv("BLOB_CONTAINER_STATE", "confluence-state")    # State tracking for changes


def get_blob_service_client():
    """Create and return blob service client"""
    if not STORAGE_CONNECTION_STRING:
        raise ValueError("BLOB_STORAGE_CONNECTION_STRING not set in .env")
    
    # Create client with connection_verify=False for corporate networks with self-signed certs
    from azure.storage.blob import BlobServiceClient
    import ssl
    
    # Disable SSL verification for corporate networks
    import certifi
    
    return BlobServiceClient.from_connection_string(
        STORAGE_CONNECTION_STRING,
        connection_verify=False  # Bypass SSL verification for corporate networks
    )


def ensure_container_exists(blob_service_client, container_name):
    """
    Create container if it doesn't exist
    
    Args:
        blob_service_client: BlobServiceClient instance
        container_name: Name of the container to create
    
    Returns:
        True if container exists or was created successfully
    """
    try:
        container_client = blob_service_client.get_container_client(container_name)
        
        # Check if container exists
        if not container_client.exists():
            print(f"   📦 Creating container: {container_name}")
            container_client.create_container()
            print(f"      ✅ Container created")
        
        return True
        
    except Exception as e:
        print(f"      ❌ Error with container {container_name}: {e}")
        return False


def upload_file_to_blob(blob_service_client, container_name, local_path, blob_path, content_type=None):
    """
    Upload a file to Azure Blob Storage
    
    Args:
        blob_service_client: BlobServiceClient instance
        container_name: Name of the container
        local_path: Local file path
        blob_path: Blob path (including folder structure)
        content_type: MIME type (auto-detected if None)
    
    Returns:
        Blob URL
    """
    # Get blob client
    blob_client = blob_service_client.get_blob_client(
        container=container_name,
        blob=blob_path
    )
    
    # Auto-detect content type if not provided
    if content_type is None:
        ext = Path(local_path).suffix.lower()
        content_type_map = {
            '.json': 'application/json',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.txt': 'text/plain'
        }
        content_type = content_type_map.get(ext, 'application/octet-stream')
    
    # Upload file
    with open(local_path, 'rb') as data:
        blob_client.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type)
        )
    
    # Return blob URL
    return blob_client.url


def sanitize_filename(text):
    """Convert text to a safe filename"""
    # Remove special characters, replace spaces with underscores
    import re
    safe_text = re.sub(r'[^\w\s-]', '', text)
    safe_text = re.sub(r'[-\s]+', '_', safe_text)
    return safe_text.strip('_')


def upload_page_to_blob(document_folder_path, update_json=True, upload_to_rag_container=True):
    """
    Upload a complete page (document.json + images) to blob storage.
    Updates document.json with blob URLs.
    
    Args:
        document_folder_path: Path to folder containing document.json and images/
        update_json: If True, update document.json with blob URLs
        upload_to_rag_container: If True, also upload to RAG-ready container with descriptive name
    
    Returns:
        dict with upload results
    """
    doc_folder = Path(document_folder_path)
    doc_json_path = doc_folder / "document.json"
    
    if not doc_json_path.exists():
        return {"success": False, "error": "document.json not found"}
    
    # Load document
    with open(doc_json_path, 'r', encoding='utf-8') as f:
        document = json.load(f)
    
    metadata = document['metadata']
    space_key = metadata['space_key']
    page_id = metadata['page_id']
    version = metadata['version']
    page_title = metadata['title']
    
    # Create sanitized filename from page title
    safe_title = sanitize_filename(page_title)
    doc_filename = f"{safe_title}_{page_id}_v{version}.json"
    
    print(f"\n{'='*70}")
    print(f"Uploading to Blob Storage: {page_title}")
    print(f"{'='*70}")
    print(f"📁 Space: {space_key}")
    print(f"📄 Page ID: {page_id}")
    print(f"📋 Version: {version}")
    print(f"📝 Document filename: {doc_filename}")
    
    # Initialize blob service
    blob_service = get_blob_service_client()
    
    # Ensure containers exist
    print(f"\n📦 Checking/creating containers...")
    ensure_container_exists(blob_service, CONTAINER_MEDIA)
    ensure_container_exists(blob_service, CONTAINER_RAG)
    
    # Base paths in blob storage
    media_base_path = f"{space_key}/{page_id}/v{version}"
    rag_blob_path = f"{space_key}/{doc_filename}"
    
    uploaded_files = []
    uploaded_images = {}
    
    # Upload images to MEDIA container
    images_folder = doc_folder / "images"
    if images_folder.exists():
        print(f"\n📤 Uploading images to MEDIA container ({CONTAINER_MEDIA})...")
        
        for image_file in images_folder.iterdir():
            if image_file.is_file():
                # Blob path for image in media container
                blob_path = f"{media_base_path}/{image_file.name}"
                
                print(f"   ⬆️ {image_file.name}...")
                
                try:
                    blob_url = upload_file_to_blob(
                        blob_service,
                        CONTAINER_MEDIA,
                        str(image_file),
                        blob_path
                    )
                    
                    # Store mapping of local filename to blob URL
                    uploaded_images[image_file.name] = blob_url
                    uploaded_files.append({
                        "file": image_file.name,
                        "blob_path": blob_path,
                        "blob_url": blob_url,
                        "container": CONTAINER_MEDIA
                    })
                    
                    print(f"      ✅ {blob_url}")
                    
                except Exception as e:
                    print(f"      ❌ Error: {e}")
    
    # Update document.json with blob URLs
    if update_json:
        print(f"\n📝 Updating document.json with blob URLs...")
        
        for block in document['content_blocks']:
            if block['type'] == 'image' and block.get('local_path'):
                # Extract filename from local path
                filename = Path(block['local_path']).name
                
                # Add blob URL if image was uploaded
                if filename in uploaded_images:
                    block['blob_url'] = uploaded_images[filename]
                    print(f"   ✅ Updated: {filename}")
        
        # Update metadata
        document['metadata']['uploaded_to_blob'] = True
        document['metadata']['blob_container_media'] = CONTAINER_MEDIA
        document['metadata']['blob_container_rag'] = CONTAINER_RAG
        document['metadata']['media_base_path'] = media_base_path
        
        # Save updated document.json locally
        with open(doc_json_path, 'w', encoding='utf-8') as f:
            json.dump(document, f, indent=2, ensure_ascii=False)
    
    # Upload to RAG container with descriptive filename
    print(f"\n📤 Uploading to RAG container ({CONTAINER_RAG})...")
    
    try:
        rag_blob_url = upload_file_to_blob(
            blob_service,
            CONTAINER_RAG,
            str(doc_json_path),
            rag_blob_path,
            content_type='application/json'
        )
        
        uploaded_files.append({
            "file": doc_filename,
            "blob_path": rag_blob_path,
            "blob_url": rag_blob_url,
            "container": CONTAINER_RAG
        })
        
        print(f"   ✅ {rag_blob_url}")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return {"success": False, "error": str(e)}
    
    # Summary
    print(f"\n{'='*70}")
    print(f"✅ UPLOAD COMPLETE")
    print(f"{'='*70}")
    print(f"📦 Total files uploaded: {len(uploaded_files)}")
    print(f"🖼️ Images in MEDIA: {len(uploaded_images)}")
    print(f"📄 RAG document: {doc_filename}")
    print(f"\nContainers:")
    print(f"  • {CONTAINER_MEDIA}: Images/media files")
    print(f"  • {CONTAINER_RAG}: RAG-ready JSON")
    
    return {
        "success": True,
        "space_key": space_key,
        "page_id": page_id,
        "version": version,
        "page_title": page_title,
        "media_base_path": media_base_path,
        "rag_blob_url": rag_blob_url,
        "rag_filename": doc_filename,
        "uploaded_files": uploaded_files,
        "image_count": len(uploaded_images)
    }


def upload_multiple_pages(data_folder="data/pages"):
    """
    Upload all pages found in the data folder
    
    Args:
        data_folder: Root folder containing space folders
    
    Returns:
        list of upload results
    """
    data_path = Path(data_folder)
    
    if not data_path.exists():
        print(f"❌ Data folder not found: {data_folder}")
        return []
    
    results = []
    
    # Find all document.json files
    for doc_json in data_path.rglob("document.json"):
        doc_folder = doc_json.parent
        
        try:
            result = upload_page_to_blob(str(doc_folder))
            results.append(result)
        except Exception as e:
            print(f"❌ Error uploading {doc_folder}: {e}")
            results.append({
                "success": False,
                "folder": str(doc_folder),
                "error": str(e)
            })
    
    # Summary
    print(f"\n{'='*70}")
    print(f"BATCH UPLOAD SUMMARY")
    print(f"{'='*70}")
    
    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]
    
    print(f"✅ Successful: {len(successful)}")
    print(f"❌ Failed: {len(failed)}")
    
    return results


def main():
    """Main entry point"""
    
    print("=" * 70)
    print("AZURE BLOB STORAGE UPLOADER")
    print("=" * 70)
    
    # Check if connection string is set
    if not STORAGE_CONNECTION_STRING:
        print("\n❌ ERROR: BLOB_STORAGE_CONNECTION_STRING not set in .env")
        print("\nPlease add to .env:")
        print("BLOB_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...")
        print("BLOB_CONTAINER_PAGES=confluence-pages")
        return
    
    # Upload the ProPM Roles & Responsibilities page
    doc_folder = "data/pages/CIPPMOPF/164168599"
    
    if Path(doc_folder).exists():
        result = upload_page_to_blob(doc_folder)
        
        if result['success']:
            print(f"\n🎉 Success! Document available at:")
            print(f"   {result['document_blob_url']}")
    else:
        print(f"❌ Document folder not found: {doc_folder}")
        print("Run confluence_content_extractor.py first!")


if __name__ == "__main__":
    main()
