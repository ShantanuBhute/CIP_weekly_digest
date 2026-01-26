# Azure Storage Account Setup Guide

## 1. Create Storage Account in Azure Portal

### Steps:
1. Go to **Azure Portal** → Search for "Storage accounts"
2. Click **"+ Create"**
3. Fill in:
   - **Subscription**: Your Azure subscription
   - **Resource Group**: Create new or use existing (e.g., `rg-confluence-digest`)
   - **Storage account name**: Unique name (e.g., `stconfluencecip`)
   - **Region**: Choose closest to you (e.g., `East US`)
   - **Performance**: Standard
   - **Redundancy**: LRS (Locally Redundant Storage) is fine for dev
4. Click **"Review + Create"** → **"Create"**

## 2. Get Connection String

After storage account is created:

1. Go to your Storage Account
2. Left menu → **"Access keys"**
3. Click **"Show keys"**
4. Copy **"Connection string"** under **key1**

It looks like:
```
DefaultEndpointsProtocol=https;AccountName=stconfluencecip;AccountKey=aBcD1234...;EndpointSuffix=core.windows.net
```

## 3. Update .env File

Paste the connection string in your `.env`:

```env
BLOB_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=stconfluencecip;AccountKey=YOUR_KEY_HERE;EndpointSuffix=core.windows.net
BLOB_CONTAINER_MEDIA=confluence-media
BLOB_CONTAINER_RAG=confluence-rag
BLOB_CONTAINER_STATE=confluence-state
```

## 4. Container Structure (Auto-created by script)

The script will automatically create these 3 containers:

### 📁 `confluence-media` (Media files)
```
confluence-media/
├── CIPPMOPF/
│   └── 164168599/
│       └── v11/
│           ├── 000_image-20240607-074813.png
│           ├── 001_image-20240605-155658.png
│           └── ...
└── CIPPMOPF/
    └── 17368537/
        └── v42/
            └── ...
```

### 📁 `confluence-rag` (RAG-ready JSON documents)
```
confluence-rag/
└── CIPPMOPF/
    ├── ProPM_Roles_Responsibilities_164168599_v11.json      ← Easy to identify!
    ├── CIP_Project_Workflow_17368537_v42.json
    ├── JIRA_Roles_Responsibilities_166039198_v48.json
    └── ...
```

### 📁 `confluence-state` (Change tracking)
```
confluence-state/
└── pages_state.json    ← Tracks versions/hashes to detect changes
```

## 5. Benefits of This Structure

✅ **Media separated** - All images in one place, versioned by page
✅ **RAG-optimized** - Descriptive filenames for easy indexing
✅ **Incremental updates** - State tracking prevents re-processing unchanged pages
✅ **Multi-version support** - Keep history (v11, v12, v13...)
✅ **Azure AI Search ready** - Can index `confluence-rag` container directly

## 6. For Incremental Updates (Future)

The state file will track:
```json
{
  "last_sync": "2026-01-26T10:30:00Z",
  "pages": {
    "164168599": {
      "version": 11,
      "content_hash": "abc123...",
      "last_modified": "2024-10-14T09:07:27Z",
      "blob_url": "https://..."
    }
  }
}
```

**Logic**: 
- Compare current page version/hash with state
- If changed → Upload to blob
- If unchanged → Skip (save time & costs!)

## 7. Test the Upload

```bash
# Install Azure Storage package
pip install azure-storage-blob

# Run the uploader
python blob_storage_uploader.py
```

## 8. Verify in Azure Portal

After upload:
1. Go to Storage Account → **Containers**
2. You should see: `confluence-media`, `confluence-rag`, `confluence-state`
3. Browse into `confluence-rag/CIPPMOPF/` to see your JSON file!

## Next Steps

After successful upload:
1. Create Azure AI Search index
2. Configure indexer to read from `confluence-rag` container
3. Enable multimodal RAG (text + image embeddings)
4. Build the summarizer!
