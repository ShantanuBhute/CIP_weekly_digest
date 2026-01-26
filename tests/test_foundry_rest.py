"""
Test Microsoft Foundry embedding API using direct REST calls
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

endpoint = os.getenv("FOUNDRY_EMBEDDING_ENDPOINT")
api_key = os.getenv("FOUNDRY_EMBEDDING_API_KEY")

print(f"Testing endpoint: {endpoint}\n")

# Test different endpoint paths
test_urls = [
    endpoint,
    f"{endpoint}/embeddings",
    endpoint.replace("/api/projects/", "/openai/deployments/") + "/embeddings",
]

for url in test_urls:
    print(f"\nTesting URL: {url}")
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key
    }
    
    payload = {
        "input": "test embedding",
        "model": "text-embedding-3-small"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, verify=False)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print(f"✅ SUCCESS!")
            data = response.json()
            if 'data' in data and len(data['data']) > 0:
                print(f"Embedding dimension: {len(data['data'][0]['embedding'])}")
            break
        else:
            print(f"Response: {response.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")
