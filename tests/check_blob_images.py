"""Quick test to check blob content for images"""
import json
import sys
import os

from azure.storage.blob import BlobServiceClient

# Load env from current directory
from dotenv import load_dotenv
load_dotenv()

STORAGE_CONNECTION_STRING = os.environ.get('BLOB_STORAGE_CONNECTION_STRING')

if not STORAGE_CONNECTION_STRING:
    # Try loading from parent
    load_dotenv('../.env')
    STORAGE_CONNECTION_STRING = os.environ.get('BLOB_STORAGE_CONNECTION_STRING')

if not STORAGE_CONNECTION_STRING:
    print("ERROR: STORAGE_CONNECTION_STRING not found")
    sys.exit(1)

blob_service = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING, connection_verify=False)
container = blob_service.get_container_client('confluence-rag')

# Check all pages
prefix = 'CIPPMOPF/'
found_any = False

# Check all blobs for any page
for blob in container.list_blobs(name_starts_with=prefix):
    # Get page ID from blob name - look at last version of each page
    print(f"Checking: {blob.name}")
        found_any = True
        print(f"Found blob: {blob.name}")
        
        blob_client = container.get_blob_client(blob.name)
        content = json.loads(blob_client.download_blob().readall())
        
        print(f"  Version: {content['metadata']['version']}")
        print(f"  Total blocks: {len(content['content_blocks'])}")
        print(f"  Images described: {content['metadata'].get('images_described', False)}")
        print(f"  Total images: {content['metadata'].get('total_images', 0)}")
        
        print("\n  Blocks breakdown:")
        for i, block in enumerate(content['content_blocks']):
            block_type = block['type']
            if block_type == 'image':
                print(f"    [{i}] IMAGE: {block.get('filename', 'unknown')}")
                print(f"         Has description: {bool(block.get('description'))}")
                if block.get('description'):
                    print(f"         Desc type: {block.get('description_type', 'unknown')}")
                    print(f"         Desc preview: {block['description'][:100]}...")
            elif block_type == 'text':
                preview = block.get('content', '')[:60].replace('\n', ' ')
                print(f"    [{i}] TEXT: {preview}...")
            elif block_type == 'heading':
                print(f"    [{i}] HEADING: {block.get('content', '')[:60]}")
            elif block_type == 'list':
                print(f"    [{i}] LIST: {len(block.get('items', []))} items")
            else:
                print(f"    [{i}] {block_type.upper()}")

if not found_any:
    print("No blobs found matching pattern for page 17386855")
