"""
Azure AI Search Indexer - Programmatic Setup
Reads from confluence-rag blob container and creates search index
"""

import os
import json
import urllib3
import httpx
import time
from pathlib import Path
from dotenv import load_dotenv
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
)
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI
from azure.core.exceptions import HttpResponseError

# Load environment variables
load_dotenv()

# Disable SSL warnings for corporate networks
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Azure AI Search configuration
SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")
SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "confluence-rag-index")

# Azure Storage configuration
STORAGE_CONNECTION_STRING = os.getenv("BLOB_STORAGE_CONNECTION_STRING")
CONTAINER_RAG = os.getenv("BLOB_CONTAINER_RAG", "confluence-rag")

# Azure OpenAI for embeddings - using Microsoft Foundry endpoint
openai_client = AzureOpenAI(
    azure_endpoint=os.getenv("FOUNDRY_EMBEDDING_ENDPOINT"),
    api_key=os.getenv("FOUNDRY_EMBEDDING_API_KEY"),
    api_version="2024-02-01",
    http_client=httpx.Client(verify=False)
)

EMBEDDING_MODEL = os.getenv("FOUNDRY_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")


def create_search_index():
    """
    Create Azure AI Search index for Confluence content with vector search
    """
    print("\n" + "=" * 70)
    print("CREATING AZURE AI SEARCH INDEX")
    print("=" * 70)
    
    # Create index client
    credential = AzureKeyCredential(SEARCH_API_KEY)
    index_client = SearchIndexClient(
        endpoint=SEARCH_ENDPOINT,
        credential=credential,
        connection_verify=False
    )
    
    # Define index schema
    fields = [
        SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="page_id", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="page_title", type=SearchFieldDataType.String),
        SearchableField(name="space_key", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="version", type=SearchFieldDataType.Int32, filterable=True),
        SimpleField(name="chunk_index", type=SearchFieldDataType.Int32),
        SearchableField(name="content_type", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="content_text", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=1536,  # text-embedding-3-small dimension
            vector_search_profile_name="myHnswProfile"
        ),
        SimpleField(name="has_image", type=SearchFieldDataType.Boolean, filterable=True),
        SimpleField(name="image_url", type=SearchFieldDataType.String, filterable=False),
        SearchableField(name="image_description", type=SearchFieldDataType.String),
        SimpleField(name="page_url", type=SearchFieldDataType.String),
        SimpleField(name="last_modified", type=SearchFieldDataType.String),
    ]
    
    # Configure vector search
    vector_search = VectorSearch(
        profiles=[
            VectorSearchProfile(
                name="myHnswProfile",
                algorithm_configuration_name="myHnsw",
            )
        ],
        algorithms=[
            HnswAlgorithmConfiguration(name="myHnsw")
        ],
    )
    
    # Create index
    index = SearchIndex(
        name=SEARCH_INDEX_NAME,
        fields=fields,
        vector_search=vector_search
    )
    
    try:
        result = index_client.create_or_update_index(index)
        print(f"✅ Index created: {result.name}")
        return True
    except Exception as e:
        print(f"❌ Failed to create index: {e}")
        return False


def delete_page_chunks(page_id):
    """
    Delete all existing chunks for a specific page from the search index.
    This should be called BEFORE re-indexing a changed page to avoid duplicates.
    
    Args:
        page_id: The Confluence page ID whose chunks should be deleted
    
    Returns:
        Number of chunks deleted
    """
    print(f"\n🗑️  Deleting existing chunks for page {page_id}...")
    
    credential = AzureKeyCredential(SEARCH_API_KEY)
    search_client = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=SEARCH_INDEX_NAME,
        credential=credential,
        connection_verify=False
    )
    
    try:
        # Find all chunks for this page
        results = search_client.search(
            search_text="*",
            filter=f"page_id eq '{page_id}'",
            select=["chunk_id"]
        )
        
        # Collect chunk IDs to delete
        chunk_ids = [doc['chunk_id'] for doc in results]
        
        if not chunk_ids:
            print(f"   No existing chunks found for page {page_id}")
            return 0
        
        print(f"   Found {len(chunk_ids)} existing chunks to delete")
        
        # Delete chunks in batches
        batch_size = 100
        deleted_count = 0
        
        for i in range(0, len(chunk_ids), batch_size):
            batch = chunk_ids[i:i + batch_size]
            documents_to_delete = [{"chunk_id": cid} for cid in batch]
            
            result = search_client.delete_documents(documents=documents_to_delete)
            deleted_count += len(batch)
            print(f"   Deleted batch {i // batch_size + 1}: {len(batch)} chunks")
        
        print(f"✅ Deleted {deleted_count} chunks for page {page_id}")
        return deleted_count
        
    except Exception as e:
        print(f"⚠️  Error deleting chunks: {e}")
        return 0


def generate_embedding(text, retry_count=3, retry_delay=2):
    """Generate embedding for text using Azure OpenAI with retry logic"""
    for attempt in range(retry_count):
        try:
            response = openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate limit" in error_msg.lower():
                if attempt < retry_count - 1:
                    wait_time = retry_delay * (attempt + 1)
                    print(f"   ⏳ Rate limit hit, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
            print(f"   ⚠️ Embedding error: {e}")
            return None
    return None


def is_heading_like(block):
    """
    Determine if a block should be treated as a heading/section marker.
    A block is heading-like if:
    - It's explicitly a heading type
    - It's a short text block (less than 100 chars or less than 20 words)
    """
    if block['type'] == 'heading':
        return True
    
    if block['type'] == 'text':
        content = block.get('content', '')
        word_count = len(content.split())
        char_count = len(content)
        
        # Short text blocks are treated as section headers
        if char_count < 100 or word_count < 20:
            return True
    
    return False


def chunk_document_semantic(document):
    """
    Convert document.json into search-ready chunks using SEMANTIC chunking.
    Groups content by heading: each heading + all content until next heading = 1 chunk.
    
    Args:
        document: Loaded document.json content
    
    Returns:
        List of chunk documents ready for indexing
    """
    chunks = []
    metadata = document['metadata']
    content_blocks = document['content_blocks']
    
    if not content_blocks:
        return chunks
    
    # Group blocks by heading sections
    sections = []
    current_section = {
        'heading': None,
        'blocks': [],
        'start_index': 0
    }
    
    for block in content_blocks:
        if is_heading_like(block):
            # Save previous section if it has content
            if current_section['blocks'] or current_section['heading']:
                sections.append(current_section)
            
            # Start new section
            current_section = {
                'heading': block.get('content', '') if block['type'] in ['heading', 'text'] else None,
                'heading_level': block.get('level', 2) if block['type'] == 'heading' else 3,
                'blocks': [block],
                'start_index': block['index']
            }
        else:
            # Add to current section
            current_section['blocks'].append(block)
    
    # Don't forget the last section
    if current_section['blocks'] or current_section['heading']:
        sections.append(current_section)
    
    print(f"   📚 Grouped into {len(sections)} semantic sections")
    
    # Convert sections to chunks
    for section_idx, section in enumerate(sections):
        chunk_id = f"{metadata['page_id']}_v{metadata['version']}_section_{section_idx:03d}"
        
        # Build section text
        content_parts = []
        has_image = False
        image_urls = []  # Collect all image URLs
        image_descriptions = []  # Collect ALL image descriptions in this section
        
        # Add heading
        if section['heading']:
            heading_prefix = '#' * section.get('heading_level', 2)
            content_parts.append(f"{heading_prefix} {section['heading']}")
        
        # Process all blocks in section
        for block in section['blocks']:
            if block['type'] == 'heading':
                # Already added as section heading, skip duplicate
                continue
            
            elif block['type'] == 'text':
                # Skip if this was the heading-like text
                if block.get('content', '') == section['heading']:
                    continue
                content_parts.append(block['content'])
            
            elif block['type'] == 'list':
                items = '\n'.join([f"• {item}" for item in block.get('items', [])])
                content_parts.append(items)
            
            elif block['type'] == 'table':
                rows = block.get('rows', [])
                table_text = "TABLE:\n" + '\n'.join([' | '.join(str(cell) for cell in row) for row in rows])
                content_parts.append(table_text)
            
            elif block['type'] == 'image':
                has_image = True
                # Get image URL - check blob_url first, then external_url
                img_url = block.get('blob_url', '') or block.get('external_url', '')
                if img_url:
                    image_urls.append(img_url)
                
                # Get description - prioritize GPT-generated description over filename
                desc = block.get('description', '')
                filename = block.get('filename', 'image')
                desc_type = block.get('description_type', 'general')
                source_type = block.get('source', 'unknown')  # 'attachment' or 'external_url'
                
                print(f"      📷 Found image: {filename} (source: {source_type}, has_desc: {bool(desc)})")
                
                if desc:
                    image_descriptions.append(f"[{desc_type.upper()}] {filename}: {desc}")
                    content_parts.append(f"\n📷 IMAGE ({desc_type}): {filename}\n{desc}\n")
                else:
                    content_parts.append(f"[IMAGE: {filename}]")
            
            else:
                content_parts.append(str(block.get('content', '')))
        
        content_text = '\n\n'.join(content_parts)
        
        # Skip empty sections
        if not content_text.strip():
            continue
        
        # Debug: show image count for this section
        if image_descriptions:
            print(f"      ✅ Section has {len(image_descriptions)} image(s) with descriptions")
        
        # Generate embedding for the entire section
        section_name = section['heading'][:50] if section['heading'] else f"Section {section_idx}"
        print(f"   🔄 Section {section_idx:03d}: {section_name}...")
        
        embedding = generate_embedding(content_text[:8000])  # Limit to 8K chars
        
        # Add delay between embedding calls to avoid rate limits
        time.sleep(0.5)
        
        if embedding:
            # Combine all image descriptions into one field (for search retrieval)
            combined_image_desc = "\n\n".join(image_descriptions) if image_descriptions else None
            
            # For image_url, store all URLs as comma-separated if multiple
            all_image_urls = ", ".join(image_urls) if image_urls else None
            
            # Debug: show what we're indexing
            if image_descriptions:
                print(f"      📝 Indexing {len(image_descriptions)} image description(s)")
                print(f"      📎 Image URLs: {len(image_urls)}")
            
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
                "image_url": all_image_urls,  # Now contains ALL image URLs
                "image_description": combined_image_desc,  # Contains ALL image descriptions
                "page_url": metadata['url'],
                "last_modified": metadata['last_modified']
            }
            
            chunks.append(chunk)
    
    return chunks


def chunk_document(document):
    """
    Convert document.json into search-ready chunks.
    Now uses SEMANTIC chunking - groups heading + content until next heading.
    
    Args:
        document: Loaded document.json content
    
    Returns:
        List of chunk documents ready for indexing
    """
    # Use semantic chunking strategy
    return chunk_document_semantic(document)


def find_blob_for_page(container_client, page_id, space_key):
    """
    Find the LATEST blob document for a specific page.
    Blobs are stored as: {space_key}/{title}_{page_id}_v{version}.json
    
    Args:
        container_client: Azure blob container client
        page_id: Confluence page ID
        space_key: Space key
    
    Returns:
        Blob name of the latest version if found, None otherwise
    """
    import re
    
    # List all blobs in the space folder and find all matching the page_id
    prefix = f"{space_key}/"
    blobs = container_client.list_blobs(name_starts_with=prefix)
    
    matching_blobs = []
    for blob in blobs:
        # Blob format: CIPPMOPF/PageTitle_12345_v1.json
        blob_name = blob.name
        # Extract page_id from blob name (look for _{page_id}_v pattern)
        if f"_{page_id}_v" in blob_name and blob_name.endswith('.json'):
            # Extract version number
            match = re.search(r'_v(\d+)\.json$', blob_name)
            if match:
                version = int(match.group(1))
                matching_blobs.append((version, blob_name))
    
    if not matching_blobs:
        return None
    
    # Sort by version and return the latest
    matching_blobs.sort(key=lambda x: x[0], reverse=True)
    latest_blob = matching_blobs[0][1]
    
    if len(matching_blobs) > 1:
        print(f"   📋 Found {len(matching_blobs)} versions, using latest: v{matching_blobs[0][0]}")
    
    return latest_blob
    
    return None


def index_single_page(page_id, space_key, delete_existing=True):
    """
    Index a single page's document.json from blob storage.
    Optionally deletes existing chunks first to avoid duplicates.
    
    Args:
        page_id: Confluence page ID
        space_key: Space key
        delete_existing: If True, delete old chunks before indexing
    
    Returns:
        Number of chunks indexed
    """
    print(f"\n📄 Indexing page {page_id}...")
    
    # Delete existing chunks first if requested
    if delete_existing:
        delete_page_chunks(page_id)
    
    # Connect to blob storage
    blob_service = BlobServiceClient.from_connection_string(
        STORAGE_CONNECTION_STRING,
        connection_verify=False
    )
    container_client = blob_service.get_container_client(CONTAINER_RAG)
    
    # Connect to search service
    credential = AzureKeyCredential(SEARCH_API_KEY)
    search_client = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=SEARCH_INDEX_NAME,
        credential=credential,
        connection_verify=False
    )
    
    # Find the document for this page
    blob_name = find_blob_for_page(container_client, page_id, space_key)
    
    if not blob_name:
        print(f"   ❌ No blob found for page {page_id} in container {CONTAINER_RAG}")
        print(f"      Expected pattern: {space_key}/*_{page_id}_v*.json")
        return 0
    
    print(f"   ✅ Found blob: {blob_name}")
    
    try:
        blob_client = container_client.get_blob_client(blob_name)
        content = blob_client.download_blob().readall()
        document = json.loads(content)
        
        # Chunk document
        chunks = chunk_document(document)
        
        if chunks:
            print(f"   ⬆️ Uploading {len(chunks)} chunks to index...")
            
            # Upload in batches with retry logic
            batch_size = 50  # Smaller batches to avoid rate limits
            total_indexed = 0
            
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                batch_num = i // batch_size + 1
                
                # Retry logic for batch upload
                max_retries = 3
                for retry in range(max_retries):
                    try:
                        result = search_client.upload_documents(documents=batch)
                        total_indexed += len(result)
                        print(f"      ✅ Batch {batch_num}: {len(result)} chunks uploaded")
                        break
                    except HttpResponseError as e:
                        if e.status_code == 429 and retry < max_retries - 1:
                            wait_time = 5 * (retry + 1)
                            print(f"      ⏳ Rate limit on batch {batch_num}, waiting {wait_time}s...")
                            time.sleep(wait_time)
                        else:
                            print(f"      ❌ Batch {batch_num} failed: {e}")
                            break
                    except Exception as e:
                        print(f"      ❌ Batch {batch_num} error: {e}")
                        break
                
                # Add delay between batches
                if i + batch_size < len(chunks):
                    time.sleep(2)  # 2 second delay between batches
            
            print(f"   ✅ Indexed {total_indexed} chunks for page {page_id}")
            return total_indexed
        
        return 0
        
    except Exception as e:
        print(f"   ❌ Error indexing page {page_id}: {e}")
        import traceback
        traceback.print_exc()
        return 0


def index_documents_from_blob():
    """
    Read all documents from confluence-rag container and index them
    """
    print("\n" + "=" * 70)
    print("INDEXING DOCUMENTS FROM BLOB STORAGE")
    print("=" * 70)
    
    # Connect to blob storage
    blob_service = BlobServiceClient.from_connection_string(
        STORAGE_CONNECTION_STRING,
        connection_verify=False
    )
    container_client = blob_service.get_container_client(CONTAINER_RAG)
    
    # Connect to search service
    credential = AzureKeyCredential(SEARCH_API_KEY)
    search_client = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=SEARCH_INDEX_NAME,
        credential=credential,
        connection_verify=False
    )
    
    # List all blobs in RAG container
    print(f"\n📦 Reading from container: {CONTAINER_RAG}")
    blobs = list(container_client.list_blobs())
    print(f"   Found {len(blobs)} documents")
    
    total_chunks = 0
    
    for blob in blobs:
        if not blob.name.endswith('.json'):
            continue
        
        print(f"\n📄 Processing: {blob.name}")
        
        # Download and parse document
        blob_client = container_client.get_blob_client(blob.name)
        content = blob_client.download_blob().readall()
        document = json.loads(content)
        
        # Chunk document
        chunks = chunk_document(document)
        
        if chunks:
            # Upload chunks to search index
            print(f"   ⬆️ Uploading {len(chunks)} chunks to index...")
            
            try:
                result = search_client.upload_documents(documents=chunks)
                print(f"   ✅ Indexed {len(result)} chunks")
                total_chunks += len(result)
            except Exception as e:
                print(f"   ❌ Error indexing: {e}")
    
    print(f"\n{'='*70}")
    print(f"✅ INDEXING COMPLETE")
    print(f"{'='*70}")
    print(f"📊 Total documents: {len(blobs)}")
    print(f"📦 Total chunks indexed: {total_chunks}")
    
    return total_chunks


def main():
    """Main entry point"""
    
    print("=" * 70)
    print("AZURE AI SEARCH SETUP & INDEXING")
    print("=" * 70)
    
    # Validate configuration
    if not SEARCH_ENDPOINT or "YOUR_SEARCH" in SEARCH_ENDPOINT:
        print("\n❌ Azure Search not configured!")
        print("Please update .env with:")
        print("  AZURE_SEARCH_ENDPOINT=https://cip-digest.search.windows.net")
        print("  AZURE_SEARCH_API_KEY=your-admin-key")
        return
    
    # Step 1: Create index
    if not create_search_index():
        return
    
    # Step 2: Index documents from blob
    index_documents_from_blob()
    
    print(f"\n🎉 Setup complete! Query your index at:")
    print(f"   {SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX_NAME}")


if __name__ == "__main__":
    main()
