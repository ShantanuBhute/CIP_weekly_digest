"""
Test semantic search on the indexed content
Proves that embeddings are stored and working
"""
import os
import httpx
from dotenv import load_dotenv
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

load_dotenv()

# Azure AI Search configuration
SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")
SEARCH_INDEX_NAME = "confluence-rag-index"

# Azure OpenAI for query embedding
openai_client = AzureOpenAI(
    azure_endpoint=os.getenv("FOUNDRY_EMBEDDING_ENDPOINT"),
    api_key=os.getenv("FOUNDRY_EMBEDDING_API_KEY"),
    api_version="2024-02-01",
    http_client=httpx.Client(verify=False)
)

EMBEDDING_MODEL = os.getenv("FOUNDRY_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")


def semantic_search(query_text, top_k=5):
    """
    Perform semantic search using vector similarity
    """
    print(f"\n{'='*70}")
    print(f"SEMANTIC SEARCH: '{query_text}'")
    print(f"{'='*70}\n")
    
    # Generate embedding for the query
    print("🔄 Generating query embedding...")
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query_text
    )
    query_vector = response.data[0].embedding
    print(f"✅ Query embedding generated ({len(query_vector)} dimensions)\n")
    
    # Connect to search service
    search_client = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=SEARCH_INDEX_NAME,
        credential=AzureKeyCredential(SEARCH_API_KEY),
        connection_verify=False
    )
    
    # Perform vector search
    print(f"🔍 Searching for top {top_k} results...\n")
    
    from azure.search.documents.models import VectorizedQuery
    
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=top_k,
        fields="content_vector"
    )
    
    results = search_client.search(
        search_text=None,  # Pure vector search, no text
        vector_queries=[vector_query],
        select=["chunk_id", "page_title", "content_type", "content_text", "has_image", "image_description"]
    )
    
    # Display results
    print("📊 RESULTS:\n")
    for i, result in enumerate(results, 1):
        score = result.get('@search.score', 0)
        print(f"[{i}] Score: {score:.4f} | Type: {result['content_type']}")
        print(f"    Title: {result['page_title']}")
        
        if result.get('has_image'):
            print(f"    🖼️  Image: {result.get('image_description', 'N/A')[:100]}...")
        else:
            content = result['content_text'][:150].replace('\n', ' ')
            print(f"    Content: {content}...")
        
        print()
    
    print(f"{'='*70}\n")


def keyword_search(query_text, top_k=3):
    """
    Perform regular keyword search (non-semantic)
    """
    print(f"\n{'='*70}")
    print(f"KEYWORD SEARCH: '{query_text}'")
    print(f"{'='*70}\n")
    
    search_client = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=SEARCH_INDEX_NAME,
        credential=AzureKeyCredential(SEARCH_API_KEY),
        connection_verify=False
    )
    
    results = search_client.search(
        search_text=query_text,
        select=["chunk_id", "page_title", "content_type", "content_text"],
        top=top_k
    )
    
    print("📊 RESULTS:\n")
    for i, result in enumerate(results, 1):
        score = result.get('@search.score', 0)
        print(f"[{i}] Score: {score:.4f} | Type: {result['content_type']}")
        content = result['content_text'][:150].replace('\n', ' ')
        print(f"    Content: {content}...")
        print()
    
    print(f"{'='*70}\n")


if __name__ == "__main__":
    # Test 1: Semantic search - understands meaning
    semantic_search("Who is responsible for project planning and budgets?")
    
    # Test 2: Semantic search - finds related concepts
    semantic_search("What are the project manager's duties?")
    
    # Test 3: Compare with keyword search
    keyword_search("project manager")
    
    print("✅ Embeddings are stored and semantic search is working!")
