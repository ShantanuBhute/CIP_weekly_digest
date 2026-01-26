# CIP Weekly Digest

Automated system that monitors Confluence pages for changes and generates AI-powered email digests.

## Project Structure

```
CIP_Weekly_Digest/
│
├── main.py                          ← MAIN ORCHESTRATOR (RUN THIS!)
│
├── [PIPELINE MODULES - 6 Steps]
├── single_page_monitor.py           # Step 1: Change detection
├── confluence_content_extractor.py  # Step 2: Extract content
├── image_description_generator.py   # Step 3: GPT-4o Vision
├── blob_storage_uploader.py         # Step 4: Blob storage
├── azure_search_indexer.py          # Step 5: AI Search indexing
├── email_digest_generator.py        # Step 6: Email generation
│
├── [CONFIG]
├── pages_config.py                  # Page configuration (which pages to monitor)
├── config/pages.json                # Optional: External page list
├── .env                             # API keys
├── requirements.txt                 # Dependencies
├── README.md                        # Main documentation
│
├── [DATA OUTPUT]
├── data/
│   ├── pages/{space}/{page_id}/     # Each page has its own folder
│   │   └── document.json            # Extracted content for that page
│   ├── emails/                      # Generated digests
│   └── runs/                        # Pipeline logs
│
├── docs/                            # Documentation (moved)
├── tests/                           # Test scripts (moved)
└── archive/                         # Old scripts (moved)
```

## Quick Start

```bash
# 1. Activate virtual environment
source .venv/Scripts/activate  # Windows
source .venv/bin/activate      # Linux/Mac

# 2. Run the pipeline
python main.py

# Options:
python main.py --force       # Force reprocess even if no changes
python main.py --email-only  # Only regenerate email from existing index

# 3. Check output
# Email: data/emails/digest_*.html
# Logs:  data/runs/pipeline_run_*.json
```

## Pipeline Flowchart

```
                    +-------------------+
                    |      START        |
                    +-------------------+
                            │
                            ▼
              ┌─────────────────────────────┐
              │   1. DETECT CHANGES         │
              │   single_page_monitor.py    │
              │   • Extract raw text        │
              │   • SHA256 hash compare     │
              └─────────────────────────────┘
                            │
                            ▼
                      ┌──────────┐
                      │ Changed? │
                      └──────────┘
                       ╱        ╲
                     NO          YES
                     │            │
                     │            ▼
                     │   ┌─────────────────────────────┐
                     │   │   2. EXTRACT CONTENT        │
                     │   │   confluence_content_       │
                     │   │   extractor.py              │
                     │   │   • Parse HTML blocks       │
                     │   │   • Download images         │
                     │   └─────────────────────────────┘
                     │            │
                     │            ▼
                     │   ┌─────────────────────────────┐
                     │   │   3. DESCRIBE IMAGES        │
                     │   │   image_description_        │
                     │   │   generator.py              │
                     │   │   • GPT-4o Vision API       │
                     │   └─────────────────────────────┘
                     │            │
                     │            ▼
                     │   ┌─────────────────────────────┐
                     │   │   4. UPLOAD TO BLOB         │
                     │   │   blob_storage_uploader.py  │
                     │   │   • confluence-media        │
                     │   │   • confluence-rag          │
                     │   └─────────────────────────────┘
                     │            │
                     │            ▼
                     │   ┌─────────────────────────────┐
                     │   │   5. INDEX IN AI SEARCH     │
                     │   │   azure_search_indexer.py   │
                     │   │   • Generate embeddings     │
                     │   │   • Vector search index     │
                     │   └─────────────────────────────┘
                     │            │
                     └─────┬──────┘
                           │
                           ▼
              ┌─────────────────────────────┐
              │   6. GENERATE EMAIL         │
              │   email_digest_generator.py │
              │   • Retrieve from AI Search │
              │   • GPT-4o RAG summary      │
              │   • Format HTML email       │
              └─────────────────────────────┘
                           │
                           ▼
              ┌─────────────────────────────┐
              │        OUTPUT               │
              │   • data/emails/*.html      │
              │   • data/runs/*.json        │
              └─────────────────────────────┘
                           │
                           ▼
                    +-------------------+
                    |       END         |
                    +-------------------+
```

## How It Works

1. **Change Detection**: Extracts raw text from Confluence and compares SHA256 hash with previous version
2. **Content Extraction**: If changed, parses HTML blocks (headings, text, lists, tables, images)
3. **Image Description**: Uses GPT-4o Vision to describe images for RAG context
4. **Blob Storage**: Uploads content JSON and images to Azure Blob Storage
5. **Delete Old Chunks**: Removes previous index entries for the changed page
6. **AI Search Indexing**: Creates embeddings and indexes chunks for semantic search
7. **Email Generation**: Uses RAG to generate executive summary email

## Configuring Pages to Monitor

### Option 1: Edit `pages_config.py` (Default)

```python
ACTIVE_PAGES = [
    {
        "page_id": "164168599",
        "title": "ProPM Roles & Responsibilities",
        "space_key": "CIPPMOPF"
    },
    {
        "page_id": "XXXXXXXXX",
        "title": "Another Subpage",
        "space_key": "CIPPMOPF"
    },
]
```

### Option 2: Create `config/pages.json`

```json
{
  "pages": [
    {
      "page_id": "164168599",
      "title": "ProPM Roles & Responsibilities",
      "space_key": "CIPPMOPF"
    }
  ]
}
```

### Future: Recursive Crawling (Commented in pages_config.py)

Uncomment the recursive crawling section in `pages_config.py` to automatically discover all child pages of a parent page.

## Multi-Page Architecture

Each page is processed independently:
- **Separate Folders**: `data/pages/{space}/{page_id}/document.json`
- **Independent Change Detection**: Each page has its own version hash
- **Smart Re-indexing**: When a page changes, only its chunks are deleted and re-indexed
- **Per-Page Emails**: Each page gets its own summary email

## Target Pages

Currently monitoring pages defined in `pages_config.py` or `config/pages.json`.

Default page:
- **Title:** ProPM Roles & Responsibilities
- **Page ID:** 164168599
- **Space:** CIPPMOPF
- **URL:** https://eaton-corp.atlassian.net/wiki/spaces/CIPPMOPF/pages/164168599

To add more pages, edit `pages_config.py` or create `config/pages.json`.

## Cost Optimization

| Scenario | Cost | What Runs |
|----------|------|-----------|
| No changes | ~$0.01 | Change detection + Email generation |
| Has changes | ~$0.05/page | Full pipeline per changed page |

**Smart optimization:** 
- Uses SHA256 hash comparison to skip unchanged pages
- Each page tracked independently (change one, only reprocess that one)
- Old chunks deleted before re-indexing to avoid duplicates

## Azure Resources

- **Azure OpenAI**: GPT-4o for summaries and image descriptions
- **Azure AI Search**: Vector search index for RAG
- **Azure Blob Storage**: Media and content storage

## Environment Variables (.env)

```bash
# Confluence
CONFLUENCE_BASE_URL=https://eaton-corp.atlassian.net/wiki
CONFLUENCE_USERNAME=your-email
CONFLUENCE_API_TOKEN=your-token

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o

# Azure Embeddings
FOUNDRY_EMBEDDING_ENDPOINT=https://your-endpoint.cognitiveservices.azure.com/
FOUNDRY_EMBEDDING_API_KEY=your-key
FOUNDRY_EMBEDDING_DEPLOYMENT=text-embedding-3-small

# Azure Blob Storage
AZURE_STORAGE_CONNECTION_STRING=your-connection-string

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://your-service.search.windows.net
AZURE_SEARCH_API_KEY=your-key
```
