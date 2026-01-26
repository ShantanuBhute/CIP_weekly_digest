"""
Test Microsoft Foundry embedding API to find correct version
"""
import os
import httpx
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

# Test different API versions
api_versions = [
    "2024-10-01-preview",
    "2024-08-01-preview", 
    "2024-06-01",
    "2024-05-01-preview",
    "2024-02-01",
    "2023-12-01-preview",
    "2023-05-15"
]

endpoint = os.getenv("FOUNDRY_EMBEDDING_ENDPOINT")
api_key = os.getenv("FOUNDRY_EMBEDDING_API_KEY")

print(f"Testing endpoint: {endpoint}\n")

for version in api_versions:
    try:
        print(f"Testing API version: {version}... ", end="")
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=version,
            http_client=httpx.Client(verify=False)
        )
        
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input="test"
        )
        
        print(f"✅ SUCCESS! Embedding dimension: {len(response.data[0].embedding)}")
        break
    except Exception as e:
        print(f"❌ Failed: {str(e)[:100]}")
