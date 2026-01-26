# Confluence Weekly Digest System - Complete Solution

## Overview

A complete automated system that:
1. **Detects changes** in Confluence pages (new pages, updates)
2. **Extracts content** preserving text and image order for multimodal RAG
3. **Generates AI summaries** using GPT-4o
4. **Sends weekly digest emails** with all updates
5. **Wraps everything in Azure Logic Apps** for automation

## Problem Statement Recap

Create a weekly digest system that:
- Monitors Confluence space (CIPPMOPF) for changes
- Extracts new/updated content with images
- Uses AI to summarize what changed
- Sends automated email digest every week
- Runs entirely in Azure Logic Apps workflow

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AZURE LOGIC APPS                         │
│                  (Recurrence: Weekly)                       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │  1. Detect Changes          │
        │  confluence_change_detector │
        │  - Query Confluence API     │
        │  - Compare with last state  │
        │  - Find new/updated pages   │
        └─────────────┬───────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │  2. Extract Content         │
        │  confluence_content_extractor│
        │  - Get full page content    │
        │  - Preserve text/image order│
        │  - Download images          │
        └─────────────┬───────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │  3. Describe Images         │
        │  image_description_generator│
        │  - GPT-4o Vision API        │
        │  - Generate descriptions    │
        └─────────────┬───────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │  4. Upload to Blob          │
        │  blob_storage_uploader      │
        │  - Store in confluence-rag  │
        │  - Save images separately   │
        └─────────────┬───────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │  5. Generate Summaries      │
        │  weekly_digest_summarizer   │
        │  - GPT-4o summarization     │
        │  - Create HTML email        │
        └─────────────┬───────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │  6. Send Email              │
        │  Office 365 Connector       │
        │  - Send HTML digest         │
        │  - To: team distribution    │
        └─────────────────────────────┘
```

## Files Created

### Core Pipeline Scripts

1. **confluence_change_detector.py**
   - Detects new/updated pages in Confluence space
   - Uses CQL (Confluence Query Language) to find recent changes
   - Stores state in Azure Blob Storage (confluence-state container)
   - Outputs: JSON with new_pages[], updated_pages[], summary

2. **weekly_digest_summarizer.py**
   - Extracts content from changed pages
   - Uses GPT-4o to generate concise summaries
   - Formats output as HTML email, JSON, and Markdown
   - Highlights what changed and business value

3. **run_weekly_digest.py**
   - Master orchestration script
   - Runs complete pipeline: detect → summarize → save
   - Can be called from Logic Apps or run standalone

### Existing Infrastructure (Already Built)

4. **confluence_content_extractor.py**
   - Extracts page content preserving block order
   - Handles headings, text, lists, tables, images

5. **image_description_generator.py**
   - Uses GPT-4o Vision to describe images
   - Specialized prompts for flowcharts, tables, screenshots

6. **blob_storage_uploader.py**
   - Uploads documents to confluence-rag container
   - Stores images in confluence-media with proper structure

7. **azure_search_indexer.py**
   - Creates vector search index
   - Chunks documents with embeddings
   - Enables semantic search

### Documentation

8. **LOGIC_APPS_SETUP.md**
   - Complete guide for Azure Logic Apps setup
   - Azure Functions deployment instructions
   - Cost estimates (~$6/year)
   - JSON workflow definition

## How It Works

### Weekly Workflow

**Every Friday at 9 AM:**

1. Logic App triggers recurrence
2. Calls detect-changes function/endpoint
3. If changes found:
   - Extracts content from each changed page
   - Generates AI summaries using GPT-4o
   - Creates HTML email digest
   - Sends to team email distribution
4. If no changes: Skips and terminates

### State Management

**confluence-state container** stores:
```json
{
  "space_key": "CIPPMOPF",
  "last_check_time": "2026-01-20T09:00:00",
  "pages": {
    "164168599": {
      "title": "ProPM Roles & Responsibilities",
      "version": 11,
      "last_modified": "2026-01-15T14:30:00"
    }
  }
}
```

On next run, compares current versions with stored versions to detect updates.

### Sample Digest Email

```
Subject: Weekly Confluence Digest - Jan 26, 2026

🆕 New Pages (2)

📄 CIP Project Governance Updates
   Version: 1 | Last Modified: Jan 24, 2026
   
   This page introduces the new CIP project governance framework,
   outlining approval processes, stage gates, and decision-making
   authority for projects exceeding $500K budget.

📄 Resource Allocation Guidelines
   Version: 1 | Last Modified: Jan 23, 2026
   
   Defines how resources are allocated across CIP portfolio,
   including prioritization criteria and capacity planning process.

✏️ Updated Pages (1)

📄 ProPM Roles & Responsibilities
   Version: 10 → 11 | Last Modified: Jan 22, 2026
   
   Updated Project Manager responsibilities to include new risk
   management requirements and added clarification on Resource
   Manager involvement in portfolio planning.
```

## Usage

### Manual Testing

```bash
# Test change detection
python confluence_change_detector.py CIPPMOPF 7

# Test digest generation
python run_weekly_digest.py CIPPMOPF 7

# Test semantic search
python test_semantic_search.py
```

### Azure Functions Deployment

```bash
# Create function app
az functionapp create \
  --resource-group your-rg \
  --name cip-digest-functions \
  --storage-account cipdigest \
  --runtime python \
  --runtime-version 3.11

# Deploy
func azure functionapp publish cip-digest-functions
```

### Logic Apps Setup

1. Create new Logic App (Consumption tier)
2. Add Recurrence trigger: Weekly, Friday, 9 AM
3. Add HTTP actions to call functions
4. Add Office 365 connector for email
5. Save and test

See [LOGIC_APPS_SETUP.md](LOGIC_APPS_SETUP.md) for detailed instructions.

## Configuration

All settings in `.env`:

```env
# Confluence
CONFLUENCE_URL=https://eaton-corp.atlassian.net/wiki
CONFLUENCE_EMAIL=shantanurbhute@eaton.com
CONFLUENCE_API_TOKEN=<token>

# Azure OpenAI (for GPT-4o)
AZURE_OPENAI_ENDPOINT=https://llm-try-summariser.openai.azure.com/
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o

# Azure OpenAI (for Embeddings)
FOUNDRY_EMBEDDING_ENDPOINT=https://ai-embedding-model.cognitiveservices.azure.com
FOUNDRY_EMBEDDING_API_KEY=<key>
FOUNDRY_EMBEDDING_DEPLOYMENT=text-embedding-3-small

# Azure Storage
BLOB_STORAGE_CONNECTION_STRING=<connection-string>
BLOB_CONTAINER_MEDIA=confluence-media
BLOB_CONTAINER_RAG=confluence-rag
BLOB_CONTAINER_STATE=confluence-state

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://cip-digest.search.windows.net
AZURE_SEARCH_API_KEY=<key>
AZURE_SEARCH_INDEX_NAME=confluence-rag-index
```

## Cost Breakdown

### Annual Costs (Estimated)

| Component | Cost |
|-----------|------|
| Azure Functions (2 functions, 52 runs/year) | $0 (Free tier) |
| Logic Apps (52 runs, 4 actions each) | ~$10/year |
| Azure Blob Storage (1 GB) | ~$0.50/year |
| Azure AI Search (Standard S1, on-demand) | $0 (create → use → delete) |
| Azure OpenAI GPT-4o (52 runs × ~2000 tokens) | ~$5/year |
| **Total** | **~$16/year** |

**Cost Optimization Tips:**
- Use Basic Logic Apps tier: $13/month → $5/month
- Delete AI Search index after use (recreate weekly)
- Use Azure Functions Consumption plan (free tier)
- Batch multiple pages in single GPT-4o call

## Features

✅ **Automated change detection** - Tracks page versions
✅ **Multimodal RAG** - Preserves text + image order
✅ **AI-powered summaries** - GPT-4o summarization
✅ **Image understanding** - GPT-4o Vision descriptions
✅ **Vector search** - Semantic search with embeddings
✅ **State persistence** - Blob storage for tracking
✅ **HTML email digest** - Professional formatting
✅ **Logic Apps integration** - Fully automated workflow
✅ **Cost optimized** - ~$16/year total cost
✅ **SSL bypass** - Works with corporate networks

## Next Steps

1. **Test locally**: Run `python run_weekly_digest.py CIPPMOPF 30` to test with last 30 days
2. **Deploy Functions**: Package Python scripts as Azure Functions
3. **Create Logic App**: Follow LOGIC_APPS_SETUP.md guide
4. **Configure Email**: Set up Office 365 connector with team distribution list
5. **Test Workflow**: Run manual trigger in Logic App
6. **Enable Schedule**: Activate weekly recurrence trigger

## Troubleshooting

**No changes detected:**
- Check Confluence API connectivity
- Verify space key is correct
- Confirm pages were modified within time window

**Summarization fails:**
- Check Azure OpenAI quota
- Verify GPT-4o deployment name
- Ensure content extraction worked

**Email not sending:**
- Verify Office 365 connector authentication
- Check recipient email address
- Confirm Logic App has permissions

**SSL errors:**
- All scripts already have `verify=False` configured
- Corporate proxy may need whitelisting

## Support

For issues or questions:
1. Check [LOGIC_APPS_SETUP.md](LOGIC_APPS_SETUP.md)
2. Review error logs in Azure Portal
3. Test individual components with manual scripts
