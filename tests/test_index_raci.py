"""Test indexing for RACI page specifically"""
import json
import sys
import os
import time

from azure.storage.blob import BlobServiceClient
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType, VectorSearch,
    VectorSearchProfile, HnswAlgorithmConfiguration, SearchableField, SimpleField
)
from openai import AzureOpenAI
from dotenv import load_dotenv
load_dotenv()

# Config
SEARCH_ENDPOINT = os.environ.get('AZURE_SEARCH_ENDPOINT')
SEARCH_API_KEY = os.environ.get('AZURE_SEARCH_API_KEY')
SEARCH_INDEX_NAME = 'confluence-rag-index'
STORAGE_CONNECTION_STRING = os.environ.get('BLOB_STORAGE_CONNECTION_STRING')
EMBEDDING_ENDPOINT = os.environ.get('FOUNDRY_EMBEDDING_ENDPOINT')
EMBEDDING_API_KEY = os.environ.get('FOUNDRY_EMBEDDING_API_KEY')
EMBEDDING_MODEL = os.environ.get('FOUNDRY_EMBEDDING_DEPLOYMENT', 'text-embedding-3-small')

# Clients
openai_client = AzureOpenAI(
    azure_endpoint=EMBEDDING_ENDPOINT,
    api_key=EMBEDDING_API_KEY,
    api_version="2024-02-15-preview"
)

def generate_embedding(text):
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text[:8000]
    )
    return response.data[0].embedding

def is_heading_like(block):
    if block['type'] == 'heading':
        return True
    if block['type'] == 'text':
        content = block.get('content', '')
        if len(content) < 100 or len(content.split()) < 20:
            return True
    return False

# Get document from blob
print("1. Loading document from blob...")
blob_service = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING, connection_verify=False)
container = blob_service.get_container_client('confluence-rag')
blob_client = container.get_blob_client('CIPPMOPF/RACI_17386855_v9.json')
document = json.loads(blob_client.download_blob().readall())

metadata = document['metadata']
content_blocks = document['content_blocks']

print(f"   Version: {metadata['version']}")
print(f"   Total blocks: {len(content_blocks)}")

# Group into sections
print("\n2. Grouping blocks into sections...")
sections = []
current_section = {'heading': None, 'blocks': [], 'start_index': 0}

for block in content_blocks:
    if is_heading_like(block):
        if current_section['blocks'] or current_section['heading']:
            sections.append(current_section)
        current_section = {
            'heading': block.get('content', '') if block['type'] in ['heading', 'text'] else None,
            'heading_level': block.get('level', 2) if block['type'] == 'heading' else 3,
            'blocks': [block],
            'start_index': block['index']
        }
    else:
        current_section['blocks'].append(block)

if current_section['blocks'] or current_section['heading']:
    sections.append(current_section)

print(f"   Created {len(sections)} sections")

# Create chunks
print("\n3. Creating chunks with embeddings...")
chunks = []

for section_idx, section in enumerate(sections):
    chunk_id = f"{metadata['page_id']}_v{metadata['version']}_section_{section_idx:03d}"
    
    content_parts = []
    has_image = False
    image_urls = []
    image_descriptions = []
    
    if section['heading']:
        heading_prefix = '#' * section.get('heading_level', 2)
        content_parts.append(f"{heading_prefix} {section['heading']}")
    
    for block in section['blocks']:
        if block['type'] == 'heading':
            continue
        elif block['type'] == 'text':
            if block.get('content', '') == section['heading']:
                continue
            content_parts.append(block['content'])
        elif block['type'] == 'list':
            items = '\n'.join([f"* {item}" for item in block.get('items', [])])
            content_parts.append(items)
        elif block['type'] == 'image':
            has_image = True
            img_url = block.get('blob_url', '') or block.get('external_url', '')
            if img_url:
                image_urls.append(img_url)
            desc = block.get('description', '')
            filename = block.get('filename', 'image')
            desc_type = block.get('description_type', 'general')
            
            print(f"      FOUND IMAGE: {filename}")
            print(f"         Has description: {bool(desc)}")
            print(f"         Desc type: {desc_type}")
            
            if desc:
                image_descriptions.append(f"[{desc_type.upper()}] {filename}: {desc}")
                content_parts.append(f"\nIMAGE ({desc_type}): {filename}\n{desc}\n")
        else:
            content_parts.append(str(block.get('content', '')))
    
    content_text = '\n\n'.join(content_parts)
    
    if not content_text.strip():
        continue
    
    print(f"\n   Section {section_idx}: {section['heading'][:50] if section['heading'] else 'No heading'}...")
    print(f"      Images: {len(image_descriptions)}")
    print(f"      Content length: {len(content_text)}")
    
    # Generate embedding
    print(f"      Generating embedding...")
    embedding = generate_embedding(content_text[:8000])
    
    combined_image_desc = "\n\n".join(image_descriptions) if image_descriptions else None
    all_image_urls = ", ".join(image_urls) if image_urls else None
    
    if combined_image_desc:
        print(f"      Image desc length: {len(combined_image_desc)}")
    
    chunk = {
        "chunk_id": chunk_id,
        "page_id": metadata['page_id'],
        "page_title": metadata['title'],
        "space_key": metadata['space_key'],
        "version": metadata['version'],
        "chunk_index": section_idx,
        "content_type": "section",
        "content_text": content_text[:10000],
        "content_vector": embedding,
        "has_image": has_image,
        "image_url": all_image_urls,
        "image_description": combined_image_desc,
        "page_url": metadata['url'],
        "last_modified": metadata['last_modified']
    }
    
    chunks.append(chunk)
    time.sleep(0.5)

print(f"\n4. Created {len(chunks)} chunks")

# Check what we have
for chunk in chunks:
    print(f"\n   Chunk: {chunk['chunk_id']}")
    print(f"      has_image: {chunk['has_image']}")
    print(f"      image_url: {chunk['image_url'][:50] if chunk['image_url'] else None}...")
    print(f"      image_description: {chunk['image_description'][:100] if chunk['image_description'] else None}...")

# Upload to index
print("\n5. Uploading to Azure Search...")
credential = AzureKeyCredential(SEARCH_API_KEY)
search_client = SearchClient(
    endpoint=SEARCH_ENDPOINT,
    index_name=SEARCH_INDEX_NAME,
    credential=credential,
    connection_verify=False
)

# Delete existing chunks for this page first
print("   Deleting existing chunks...")
results = search_client.search(search_text="*", filter=f"page_id eq '17386855'", select=["chunk_id"])
docs_to_delete = [{"chunk_id": doc["chunk_id"]} for doc in results]
if docs_to_delete:
    search_client.delete_documents(documents=docs_to_delete)
    print(f"   Deleted {len(docs_to_delete)} old chunks")

print("   Uploading new chunks...")
result = search_client.upload_documents(documents=chunks)
print(f"   Uploaded {len(result)} chunks")

print("\n6. Verifying upload...")
time.sleep(2)  # Wait for index to update
results = search_client.search(search_text="*", filter=f"page_id eq '17386855'", select=["chunk_id", "has_image", "image_description"])
for doc in results:
    print(f"   {doc['chunk_id']}: has_image={doc.get('has_image')}, img_desc={doc.get('image_description', 'None')[:50] if doc.get('image_description') else 'None'}...")
