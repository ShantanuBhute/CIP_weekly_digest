# CIP Confluence Digest - Azure Resources Report

## 📋 Executive Summary

This document details all Azure resources required for the **CIP Confluence Digest** system - an automated pipeline that monitors Confluence pages for changes, generates AI-powered email summaries, and sends them to subscribed users.

**Current State:** Pilot with 4 pages in CIPPMOPF space  
**Target State:** Full space monitoring → Multi-space monitoring

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            CONFLUENCE DIGEST SYSTEM                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────┐      ┌─────────────────────────────────────────────────────┐  │
│  │  Confluence  │      │              AZURE FUNCTIONS                        │  │
│  │    Pages     │─────▶│  ┌─────────────────────────────────────────────┐   │  │
│  └──────────────┘      │  │  pipeline_orchestrator (Timer: every 2 days) │   │  │
│                        │  │  run_pipeline (HTTP: manual trigger)         │   │  │
│                        │  │  health_check (HTTP: monitoring)             │   │  │
│                        │  └─────────────────────────────────────────────┘   │  │
│                        └─────────────────────────────────────────────────────┘  │
│                                         │                                        │
│                    ┌────────────────────┼────────────────────┐                  │
│                    ▼                    ▼                    ▼                  │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐     │
│  │   BLOB STORAGE      │  │   AZURE SEARCH      │  │   COSMOS DB         │     │
│  │   - confluence-media│  │   - confluence-rag  │  │   - subscriptions   │     │
│  │   - confluence-rag  │  │     -index          │  │     container       │     │
│  │   - confluence-state│  │                     │  │                     │     │
│  │   - confluence-emails│  │                     │  │                     │     │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘     │
│                                         │                                        │
│                    ┌────────────────────┼────────────────────┐                  │
│                    ▼                    ▼                    ▼                  │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐     │
│  │   AZURE OPENAI      │  │   AZURE AI SERVICES │  │   LOGIC APP         │     │
│  │   - GPT-4o          │  │   - text-embedding  │  │   - Email via       │     │
│  │     (summaries)     │  │     -3-small        │  │     Office 365      │     │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘     │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                    STREAMLIT CLOUD (External)                            │   │
│  │                    Subscription Management Portal                        │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Resource Summary Table

| Resource | Service Type | SKU/Tier | Current (4 pages) | Full Space (~100 pages) | Multi-Space (~500 pages) |
|----------|-------------|----------|-------------------|------------------------|-------------------------|
| Azure Functions | App Service | **Consumption (Y1)** | ~$0-1/month | ~$2-5/month | ~$10-20/month |
| Storage Account | Blob Storage | **Standard LRS** | ~$0.50/month | ~$2-5/month | ~$10-20/month |
| Azure AI Search | Cognitive Search | **Free/Basic** | Free tier OK | Basic ($75/mo) | Standard ($250/mo) |
| Cosmos DB | NoSQL Database | **Serverless** | ~$0-1/month | ~$2-5/month | ~$5-15/month |
| Azure OpenAI | AI Service | **S0** | ~$2-5/month | ~$20-50/month | ~$100-200/month |
| Azure AI Services | Embeddings | **S0** | ~$1-2/month | ~$5-10/month | ~$20-50/month |
| Logic App | Integration | **Consumption** | ~$0-1/month | ~$1-5/month | ~$5-20/month |
| **TOTAL** | | | **~$5-10/month** | **~$110-150/month** | **~$350-500/month** |

---

## 🔧 Detailed Resource Specifications

---

### 1️⃣ AZURE FUNCTIONS (Core Compute)

**What it does:** Hosts all the automated code that runs the pipeline.

#### Current Configuration
```
Name:           cip-digest-functions
Resource Group: testing
Region:         East US (or your preferred region)
Runtime:        Python 3.11
Plan:           Consumption (Serverless)
OS:             Linux
```

#### How Azure Functions Work

**Local Development → Cloud Deployment Flow:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LOCAL DEVELOPMENT                                                       │
│                                                                          │
│  /Azure Functions/                                                       │
│  ├── host.json              ← Global settings (timeout, logging)        │
│  ├── requirements.txt       ← Python dependencies                       │
│  ├── local.settings.json    ← Local environment variables (NOT deployed)│
│  │                                                                       │
│  ├── health_check/          ← FUNCTION #1                               │
│  │   ├── __init__.py        ← Function code                             │
│  │   └── function.json      ← Trigger type: HTTP GET                    │
│  │                                                                       │
│  ├── pipeline_orchestrator/ ← FUNCTION #2                               │
│  │   ├── __init__.py        ← Function code                             │
│  │   └── function.json      ← Trigger type: Timer (every 2 days)        │
│  │                                                                       │
│  ├── run_pipeline/          ← FUNCTION #3                               │
│  │   ├── __init__.py        ← Function code                             │
│  │   └── function.json      ← Trigger type: HTTP GET/POST               │
│  │                                                                       │
│  └── *.py                   ← Shared modules (imported by functions)    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │  func azure functionapp publish cip-digest-functions
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  AZURE CLOUD                                                             │
│                                                                          │
│  Function App: cip-digest-functions                                      │
│  ├── Functions:                                                          │
│  │   ├── health_check      → https://cip-digest-functions.../health_check│
│  │   ├── pipeline_orchestrator → Runs automatically every 2 days        │
│  │   └── run_pipeline      → https://cip-digest-functions.../run_pipeline│
│  │                                                                       │
│  ├── Application Settings (Environment Variables):                       │
│  │   ├── AZURE_STORAGE_ACCOUNT_NAME                                     │
│  │   ├── AZURE_OPENAI_ENDPOINT                                          │
│  │   ├── COSMOS_ENDPOINT                                                │
│  │   └── ... (all from .env)                                            │
│  │                                                                       │
│  └── Configuration:                                                      │
│      ├── Timeout: 9 minutes (from host.json)                            │
│      └── Python 3.11 runtime                                            │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Functions in This Project (3 Functions, 1 App)

| Function | Trigger Type | Purpose | URL/Schedule |
|----------|-------------|---------|--------------|
| `health_check` | HTTP (GET) | Verify app is running | `GET /api/health_check` |
| `pipeline_orchestrator` | Timer | Auto-run pipeline | `0 0 0 */2 * *` (every 2 days at midnight) |
| `run_pipeline` | HTTP (GET/POST) | Manual trigger | `GET/POST /api/run_pipeline` |

**Important:** It's ONE Function App containing THREE Functions. Not three separate apps.

#### Shared Modules (Not Functions, Just Python Files)

These `.py` files are shared code imported by the functions:

| Module | Purpose |
|--------|---------|
| `confluence_content_extractor.py` | Fetches content from Confluence API |
| `image_description_generator.py` | Uses GPT-4o to describe images |
| `blob_storage_uploader.py` | Uploads content to Azure Blob Storage |
| `azure_search_indexer.py` | Indexes content in Azure AI Search |
| `email_digest_generator.py` | Generates HTML email summaries using GPT-4o |
| `email_sender.py` | Sends emails via Logic App |
| `subscription_manager.py` | Manages user subscriptions in Cosmos DB |
| `single_page_monitor.py` | Detects changes in Confluence pages |
| `pages_config.py` | Configuration for monitored pages |

#### Setup Steps for DevOps Team

```bash
# 1. Create Function App
az functionapp create \
  --resource-group YOUR_RESOURCE_GROUP \
  --consumption-plan-location eastus \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --name cip-digest-functions \
  --storage-account YOUR_STORAGE_ACCOUNT \
  --os-type Linux

# 2. Configure Application Settings (Environment Variables)
az functionapp config appsettings set \
  --name cip-digest-functions \
  --resource-group YOUR_RESOURCE_GROUP \
  --settings \
    AZURE_STORAGE_ACCOUNT_NAME=cipdigest \
    AZURE_STORAGE_ACCOUNT_KEY=xxx \
    AZURE_SEARCH_ENDPOINT=https://xxx.search.windows.net \
    AZURE_SEARCH_API_KEY=xxx \
    AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com/ \
    AZURE_OPENAI_API_KEY=xxx \
    AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o \
    FOUNDRY_EMBEDDING_ENDPOINT=https://xxx.cognitiveservices.azure.com/ \
    FOUNDRY_EMBEDDING_API_KEY=xxx \
    CONFLUENCE_BASE_URL=https://eaton-corp.atlassian.net/wiki \
    CONFLUENCE_EMAIL=xxx@eaton.com \
    CONFLUENCE_API_TOKEN=xxx \
    PAGE_IDS=164168599,166041865,17386855,439124075 \
    SPACE_KEY=CIPPMOPF \
    COSMOS_ENDPOINT=https://xxx.documents.azure.com:443/ \
    COSMOS_KEY=xxx \
    LOGIC_APP_EMAIL_URL=https://xxx.logic.azure.com/xxx

# 3. Deploy code (developer runs this)
cd "Azure Functions"
func azure functionapp publish cip-digest-functions
```

#### Scaling Considerations

| Scenario | Timer Schedule | Timeout | Memory |
|----------|---------------|---------|--------|
| 4 pages (current) | Every 2 days | 9 min | 1.5 GB (default) |
| Full space (~100 pages) | Once daily | 10 min | 1.5 GB |
| Multi-space (~500 pages) | Twice daily | 10 min + parallel processing | Consider Premium plan |

---

### 2️⃣ AZURE STORAGE ACCOUNT

**What it does:** Stores all documents, images, state files, and email digests.

#### Configuration
```
Name:               cipdigest
Resource Group:     testing
Region:             East US
Performance:        Standard
Replication:        LRS (Locally Redundant)
Account kind:       StorageV2
Access tier:        Hot
```

#### Blob Containers Required

| Container | Purpose | Content Type |
|-----------|---------|--------------|
| `confluence-media` | Images and attachments from Confluence | PNG, JPG, PDF |
| `confluence-rag` | Processed documents for RAG | JSON documents |
| `confluence-state` | Pipeline state (last processed version) | JSON state files |
| `confluence-emails` | Generated email digests | HTML, JSON metadata |

#### Setup Steps

```bash
# Create storage account
az storage account create \
  --name cipdigest \
  --resource-group YOUR_RESOURCE_GROUP \
  --location eastus \
  --sku Standard_LRS \
  --kind StorageV2

# Create containers
az storage container create --name confluence-media --account-name cipdigest
az storage container create --name confluence-rag --account-name cipdigest
az storage container create --name confluence-state --account-name cipdigest
az storage container create --name confluence-emails --account-name cipdigest

# Get connection string (for environment variables)
az storage account show-connection-string --name cipdigest --resource-group YOUR_RESOURCE_GROUP
```

#### Scaling Estimates

| Scenario | Storage Size | Monthly Cost |
|----------|-------------|--------------|
| 4 pages | ~50 MB | ~$0.50 |
| 100 pages | ~2 GB | ~$2-5 |
| 500 pages | ~10 GB | ~$10-20 |

---

### 3️⃣ AZURE AI SEARCH (Cognitive Search)

**What it does:** Provides semantic search over indexed Confluence content. Used to retrieve relevant content when generating email summaries.

#### Configuration
```
Name:           cip-digest
Resource Group: testing
Region:         East US
Tier:           Free (current) → Basic/Standard (production)
Index:          confluence-rag-index
```

#### Index Schema

```json
{
  "name": "confluence-rag-index",
  "fields": [
    {"name": "id", "type": "Edm.String", "key": true},
    {"name": "page_id", "type": "Edm.String", "filterable": true},
    {"name": "space_key", "type": "Edm.String", "filterable": true},
    {"name": "page_title", "type": "Edm.String", "searchable": true},
    {"name": "content", "type": "Edm.String", "searchable": true},
    {"name": "chunk_index", "type": "Edm.Int32"},
    {"name": "version", "type": "Edm.Int32"},
    {"name": "content_vector", "type": "Collection(Edm.Single)", "dimensions": 1536}
  ]
}
```

#### Setup Steps

```bash
# Create search service
az search service create \
  --name cip-digest \
  --resource-group YOUR_RESOURCE_GROUP \
  --location eastus \
  --sku basic

# Get admin key (for environment variables)
az search admin-key show --service-name cip-digest --resource-group YOUR_RESOURCE_GROUP
```

#### Tier Recommendations

| Scenario | Tier | Documents | Cost |
|----------|------|-----------|------|
| 4 pages (~50 chunks) | Free | Up to 10,000 | Free |
| 100 pages (~1,000 chunks) | Basic | Up to 1M | $75/month |
| 500 pages (~5,000 chunks) | Standard | Up to 5M | $250/month |

---

### 4️⃣ AZURE COSMOS DB

**What it does:** Stores user subscription data - who subscribed to which pages.

#### Configuration
```
Name:               cip-digest-cosmos
Resource Group:     testing
Region:             East US
API:                Core (SQL) - NoSQL
Capacity Mode:      Serverless (pay per request)
Database:           confluence-digest
Container:          subscriptions
Partition Key:      /partitionKey
```

#### Data Structure

```json
{
  "id": "john_doe_at_eaton_com",
  "partitionKey": "subscriptions",
  "email": "john.doe@eaton.com",
  "displayName": "John Doe",
  "subscriptions": [
    {
      "pageId": "166041865",
      "pageName": "Agile - Scrum Roles & Responsibilities",
      "subscribedAt": "2026-01-28T10:00:00Z"
    },
    {
      "pageId": "17386855",
      "pageName": "RACI",
      "subscribedAt": "2026-01-28T10:00:00Z"
    }
  ],
  "preferences": {
    "frequency": "immediate"
  },
  "createdAt": "2026-01-28T10:00:00Z"
}
```

#### Setup Steps

```bash
# Create Cosmos DB account (Serverless)
az cosmosdb create \
  --name cip-digest-cosmos \
  --resource-group YOUR_RESOURCE_GROUP \
  --locations regionName=eastus \
  --capabilities EnableServerless

# Create database and container (done automatically by code, but can be done manually)
az cosmosdb sql database create \
  --account-name cip-digest-cosmos \
  --resource-group YOUR_RESOURCE_GROUP \
  --name confluence-digest

az cosmosdb sql container create \
  --account-name cip-digest-cosmos \
  --resource-group YOUR_RESOURCE_GROUP \
  --database-name confluence-digest \
  --name subscriptions \
  --partition-key-path /partitionKey

# Get connection key (for environment variables)
az cosmosdb keys list --name cip-digest-cosmos --resource-group YOUR_RESOURCE_GROUP
```

#### Scaling

| Scenario | Subscribers | RU/s | Cost |
|----------|-------------|------|------|
| 4 pages, ~50 users | ~50 | Serverless | ~$1/month |
| 100 pages, ~500 users | ~500 | Serverless | ~$5/month |
| 500 pages, ~2000 users | ~2000 | Provisioned 400 RU/s | ~$25/month |

---

### 5️⃣ AZURE OPENAI SERVICE

**What it does:** Powers AI features - image descriptions and email summary generation.

#### Configuration
```
Name:               llm-try-summariser (or new dedicated resource)
Resource Group:     testing
Region:             East US
Model Deployments:  gpt-4o
```

#### Model Deployment

| Deployment Name | Model | Purpose | TPM (Tokens/min) |
|----------------|-------|---------|------------------|
| `gpt-4o` | GPT-4o | Email summaries, image descriptions | 10K-50K |

#### Setup Steps

```bash
# Create Azure OpenAI resource
az cognitiveservices account create \
  --name cip-digest-openai \
  --resource-group YOUR_RESOURCE_GROUP \
  --location eastus \
  --kind OpenAI \
  --sku S0

# Deploy GPT-4o model (via Azure Portal or CLI)
az cognitiveservices account deployment create \
  --name cip-digest-openai \
  --resource-group YOUR_RESOURCE_GROUP \
  --deployment-name gpt-4o \
  --model-name gpt-4o \
  --model-version "2024-05-13" \
  --model-format OpenAI \
  --sku-capacity 10 \
  --sku-name Standard
```

#### Cost Estimates

| Scenario | Tokens/Month | Cost |
|----------|-------------|------|
| 4 pages (2 runs/month) | ~50K | ~$2 |
| 100 pages (daily) | ~1M | ~$30 |
| 500 pages (twice daily) | ~10M | ~$150 |

---

### 6️⃣ AZURE AI SERVICES (Embeddings)

**What it does:** Generates vector embeddings for semantic search.

#### Configuration
```
Name:               ai-embedding-model
Resource Group:     testing
Region:             East US
Model:              text-embedding-3-small
```

#### Setup Steps

```bash
# Create Azure AI Services resource
az cognitiveservices account create \
  --name cip-digest-embeddings \
  --resource-group YOUR_RESOURCE_GROUP \
  --location eastus \
  --kind AIServices \
  --sku S0

# Deploy embedding model
# (Done via Azure AI Studio / Foundry Portal)
```

---

### 7️⃣ AZURE LOGIC APP

**What it does:** Sends emails via Office 365 Outlook. Acts as bridge between Azure Functions and corporate email.

#### Configuration
```
Name:               cip-digest-email-sender
Resource Group:     testing
Region:             East US
Type:               Consumption (pay per execution)
```

#### Logic App Design

```
┌─────────────────────────────────────────────────────────────────┐
│                         LOGIC APP FLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TRIGGER: When HTTP request is received (POST)                  │
│           ├── Method: POST                                      │
│           └── Request Body JSON Schema:                         │
│               {                                                  │
│                 "to": "string",                                 │
│                 "subject": "string",                            │
│                 "body": "string"                                │
│               }                                                  │
│                              │                                   │
│                              ▼                                   │
│  ACTION: Send an email (V2) - Office 365 Outlook                │
│           ├── To: triggerBody()?['to']                          │
│           ├── Subject: triggerBody()?['subject']                │
│           └── Body: triggerBody()?['body']                      │
│                              │                                   │
│                              ▼                                   │
│  RESPONSE: HTTP 202 Accepted                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Setup Steps (Azure Portal - Manual)

1. **Create Logic App:**
   - Go to Azure Portal → Create Resource → Logic App
   - Choose "Consumption" plan
   - Name: `cip-digest-email-sender`

2. **Design the Workflow:**
   ```
   Trigger: "When a HTTP request is received"
   → Schema: {"to": "string", "subject": "string", "body": "string"}
   
   Action: "Send an email (V2)" (Office 365 Outlook)
   → Connection: Sign in with service account (e.g., cip-digest@eaton.com)
   → To: @{triggerBody()?['to']}
   → Subject: @{triggerBody()?['subject']}
   → Body: @{triggerBody()?['body']}
   ```

3. **Get HTTP URL:**
   - After saving, copy the "HTTP POST URL" from the trigger
   - This URL goes into `LOGIC_APP_EMAIL_URL` environment variable

#### Important Note
The Logic App needs to authenticate with an Office 365 account that has permission to send emails. This typically requires:
- A service account email (e.g., `cip-digest@eaton.com`)
- Or a shared mailbox with send permissions

---

## 🔐 Environment Variables Summary

All these variables must be configured in Azure Functions Application Settings:

```env
# Azure Storage
AZURE_STORAGE_ACCOUNT_NAME=cipdigest
AZURE_STORAGE_ACCOUNT_KEY=<from-storage-account>
AZURE_STORAGE_CONNECTION_STRING=<connection-string>
EMAIL_CONTAINER=confluence-emails

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://cip-digest.search.windows.net
AZURE_SEARCH_API_KEY=<from-search-service>

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://cip-digest-openai.openai.azure.com/
AZURE_OPENAI_API_KEY=<from-openai-service>
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o

# Embeddings
FOUNDRY_EMBEDDING_ENDPOINT=https://cip-digest-embeddings.cognitiveservices.azure.com/
FOUNDRY_EMBEDDING_API_KEY=<from-ai-services>
FOUNDRY_EMBEDDING_DEPLOYMENT=text-embedding-3-small

# Confluence
CONFLUENCE_BASE_URL=https://eaton-corp.atlassian.net/wiki
CONFLUENCE_EMAIL=<service-account-email>
CONFLUENCE_API_TOKEN=<confluence-api-token>
SPACE_KEY=CIPPMOPF
PAGE_IDS=164168599,166041865,17386855,439124075

# Cosmos DB
COSMOS_ENDPOINT=https://cip-digest-cosmos.documents.azure.com:443/
COSMOS_KEY=<from-cosmos-db>
COSMOS_DATABASE=confluence-digest
COSMOS_CONTAINER=subscriptions

# Logic App
LOGIC_APP_EMAIL_URL=https://<your-logic-app-url>
```

---

## 📈 Scaling Strategy

### Phase 1: Current (4 Pages)
- All resources on Free/Consumption tiers
- Cost: ~$5-10/month

### Phase 2: Full Space (~100 Pages)
- Upgrade Azure Search to Basic tier
- Increase OpenAI token quota
- Cost: ~$110-150/month

### Phase 3: Multi-Space (~500 Pages)
- Consider Azure Functions Premium plan
- Implement parallel processing
- Azure Search Standard tier
- Cost: ~$350-500/month

### Code Changes for Scaling

For full space monitoring, change from static page IDs to dynamic discovery:

```python
# Current: Static page IDs
PAGE_IDS = "164168599,166041865,17386855,439124075"

# Future: Dynamic discovery
def get_all_pages_in_space(space_key):
    """Fetch all page IDs from Confluence space"""
    response = requests.get(
        f"{CONFLUENCE_BASE_URL}/rest/api/content",
        params={"spaceKey": space_key, "limit": 500, "type": "page"},
        auth=(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)
    )
    return [page['id'] for page in response.json()['results']]
```

---

## 📋 DevOps Checklist

### Resources to Create

- [ ] Resource Group: `cip-digest-prod`
- [ ] Storage Account: `cipdigestprod` (Standard LRS)
  - [ ] Container: `confluence-media`
  - [ ] Container: `confluence-rag`
  - [ ] Container: `confluence-state`
  - [ ] Container: `confluence-emails`
- [ ] Azure AI Search: `cip-digest-search` (Basic tier)
- [ ] Azure OpenAI: `cip-digest-openai` (S0)
  - [ ] Deploy model: `gpt-4o`
- [ ] Azure AI Services: `cip-digest-embeddings` (S0)
  - [ ] Deploy model: `text-embedding-3-small`
- [ ] Cosmos DB: `cip-digest-cosmos` (Serverless)
  - [ ] Database: `confluence-digest`
  - [ ] Container: `subscriptions`
- [ ] Logic App: `cip-digest-email` (Consumption)
  - [ ] Configure Office 365 connection
- [ ] Function App: `cip-digest-functions` (Consumption, Python 3.11, Linux)
  - [ ] Configure all environment variables

### Service Account Requirements

1. **Confluence API Token:**
   - Service account with read access to target spaces
   - Generate API token from Atlassian account settings

2. **Office 365 Email:**
   - Service account or shared mailbox for sending digest emails
   - Must have "Send As" permissions

---

## 📞 Contact & Support

For questions about this architecture:
- Developer: [Your Name]
- Created: January 2026
- Last Updated: January 30, 2026

---

## 📎 Appendix: Quick Reference Commands

```bash
# Start Function App
az functionapp start --name cip-digest-functions --resource-group YOUR_RG

# Stop Function App
az functionapp stop --name cip-digest-functions --resource-group YOUR_RG

# View logs
az functionapp log tail --name cip-digest-functions --resource-group YOUR_RG

# Deploy code
cd "Azure Functions" && func azure functionapp publish cip-digest-functions

# Test health check
curl https://cip-digest-functions.azurewebsites.net/api/health_check

# Manually trigger pipeline
curl "https://cip-digest-functions.azurewebsites.net/api/run_pipeline?force_email=true"
```
