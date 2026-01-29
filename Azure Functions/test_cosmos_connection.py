"""
Test script to verify Cosmos DB connection
"""

import os
import json
from azure.cosmos import CosmosClient

# Load settings from local.settings.json
settings_path = os.path.join(os.path.dirname(__file__), "local.settings.json")

with open(settings_path, "r") as f:
    settings = json.load(f)
    values = settings.get("Values", {})

COSMOS_ENDPOINT = values.get("COSMOS_ENDPOINT")
COSMOS_KEY = values.get("COSMOS_KEY")
COSMOS_DATABASE = values.get("COSMOS_DATABASE")
COSMOS_CONTAINER = values.get("COSMOS_CONTAINER")

print("=" * 50)
print("COSMOS DB CONNECTION TEST")
print("=" * 50)
print(f"\nEndpoint: {COSMOS_ENDPOINT}")
print(f"Database: {COSMOS_DATABASE}")
print(f"Container: {COSMOS_CONTAINER}")
print(f"Key (first 20 chars): {COSMOS_KEY[:20]}...")
print()

try:
    print("1. Creating Cosmos client...")
    client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
    print("   ✅ Client created successfully")
    
    print("\n2. Getting database...")
    database = client.get_database_client(COSMOS_DATABASE)
    # Try to read database properties to verify it exists
    db_props = database.read()
    print(f"   ✅ Database '{COSMOS_DATABASE}' exists")
    
    print("\n3. Getting container...")
    container = database.get_container_client(COSMOS_CONTAINER)
    # Try to read container properties to verify it exists
    container_props = container.read()
    print(f"   ✅ Container '{COSMOS_CONTAINER}' exists")
    
    print("\n4. Querying items (limit 5)...")
    items = list(container.query_items(
        query="SELECT * FROM c",
        enable_cross_partition_query=True,
        max_item_count=5
    ))
    print(f"   ✅ Query successful - Found {len(items)} item(s)")
    
    if items:
        print("\n   Sample item keys:")
        for key in items[0].keys():
            print(f"      - {key}")
    
    print("\n" + "=" * 50)
    print("✅ ALL TESTS PASSED - Connection is working!")
    print("=" * 50)
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print("\n" + "=" * 50)
    print("❌ CONNECTION FAILED")
    print("=" * 50)
