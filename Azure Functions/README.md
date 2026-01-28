# CIP Weekly Digest - Azure Functions

Automated Confluence page monitoring and email digest system.

## Functions

1. **pipeline_orchestrator** - Timer triggered (every 5 minutes)
   - Monitors configured Confluence pages for changes
   - Generates AI-powered email summaries
   - Sends notifications to subscribers

2. **run_pipeline** - HTTP triggered
   - Manual pipeline execution
   - Supports `force=true` and `force_email=true` parameters

## Deployment

### Prerequisites
- Azure Functions Core Tools v4
- Python 3.11
- Azure CLI

### Deploy to Azure

```bash
# Login to Azure
az login

# Create Function App (if not exists)
az functionapp create \
  --resource-group cip-digest-rg \
  --consumption-plan-location eastus2 \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --name cip-digest-functions \
  --storage-account cipdigest

# Deploy
func azure functionapp publish cip-digest-functions
```

### Environment Variables

Configure these in Azure Portal > Function App > Configuration:

- `CONFLUENCE_URL`
- `CONFLUENCE_EMAIL`
- `CONFLUENCE_API_TOKEN`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_API_KEY`
- `BLOB_STORAGE_CONNECTION_STRING`
- `COSMOS_ENDPOINT`
- `COSMOS_KEY`
- `PAGE_IDS`
- `LOGIC_APP_EMAIL_URL`
