# Azure Logic Apps Workflow Setup

This document explains how to wrap the entire Confluence Weekly Digest pipeline in an Azure Logic Apps workflow.

## Overview

The Logic App will orchestrate:
1. **Detect Changes** - Run `confluence_change_detector.py` to find new/updated pages
2. **Generate Digest** - Run `weekly_digest_summarizer.py` to create summaries
3. **Send Email** - Send HTML digest via Office 365/Outlook connector

## Prerequisites

- Azure subscription with Logic Apps
- Azure Container Instances or Azure Functions to run Python scripts
- Office 365 or Outlook.com account for sending emails

## Architecture Options

### Option 1: Azure Functions (Recommended)

**Best for:** Serverless, cost-effective, scales automatically

```
Logic App (Recurrence Trigger - Weekly)
    ↓
Azure Function 1: detect_changes
    ↓ (HTTP response with changes JSON)
Azure Function 2: generate_digest  
    ↓ (HTTP response with HTML digest)
Logic App: Send Email (Office 365 connector)
```

### Option 2: Container Instances

**Best for:** Full environment control, complex dependencies

```
Logic App (Recurrence Trigger)
    ↓
Container Instance: Run entire pipeline
    ↓ (Store results in Blob Storage)
Logic App: Read from Blob
    ↓
Logic App: Send Email
```

### Option 3: Logic App HTTP Actions (Simplest)

**Best for:** Quick setup, existing API endpoints

```
Logic App (Recurrence)
    ↓
HTTP Action: POST to your hosted Python API
    ↓
Parse JSON response
    ↓
Send Email
```

## Recommended Implementation: Azure Functions

### Step 1: Create Azure Functions

Create two HTTP-triggered Python functions:

#### Function 1: `detect-changes`

```python
import azure.functions as func
import json
from confluence_change_detector import detect_changes

def main(req: func.HttpRequest) -> func.HttpResponse:
    space_key = req.params.get('space_key', 'CIPPMOPF')
    days = int(req.params.get('days', 7))
    
    changes = detect_changes(space_key, days)
    
    return func.HttpResponse(
        json.dumps(changes),
        mimetype="application/json",
        status_code=200
    )
```

#### Function 2: `generate-digest`

```python
import azure.functions as func
import json
from weekly_digest_summarizer import generate_weekly_digest, format_digest_html

def main(req: func.HttpRequest) -> func.HttpResponse:
    req_body = req.get_json()
    
    # Save changes to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        json.dump(req_body, f)
        changes_file = f.name
    
    # Generate digest
    digest = generate_weekly_digest(changes_file)
    html = format_digest_html(digest)
    
    return func.HttpResponse(
        json.dumps({
            'digest': digest,
            'html': html
        }),
        mimetype="application/json",
        status_code=200
    )
```

### Step 2: Deploy Functions

```bash
# Create Function App
az functionapp create \
  --resource-group your-rg \
  --name cip-digest-functions \
  --storage-account cipdigest \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --os-type Linux

# Deploy functions
func azure functionapp publish cip-digest-functions
```

### Step 3: Create Logic App Workflow

#### Visual Designer Flow:

```
1. Recurrence Trigger
   - Frequency: Week
   - Interval: 1
   - On these days: Friday
   - At these hours: 9
   - Time zone: (UTC-05:00) Eastern Time

2. HTTP Action: Detect Changes
   - Method: GET
   - URI: https://cip-digest-functions.azurewebsites.net/api/detect-changes?space_key=CIPPMOPF&days=7
   - Save response as: changes_response

3. Parse JSON: Parse Changes
   - Content: @body('Detect_Changes')
   - Schema: (use sample from confluence_change_detector output)

4. Condition: Check if there are updates
   - Condition: @greater(add(body('Parse_Changes')?['summary']?['total_new'], body('Parse_Changes')?['summary']?['total_updated']), 0)

5. If Yes:
   
   a. HTTP Action: Generate Digest
      - Method: POST
      - URI: https://cip-digest-functions.azurewebsites.net/api/generate-digest
      - Headers: Content-Type: application/json
      - Body: @body('Parse_Changes')
   
   b. Parse JSON: Parse Digest
      - Content: @body('Generate_Digest')
   
   c. Office 365 Outlook: Send Email
      - To: your-team@eaton.com
      - Subject: Weekly Confluence Digest - @{formatDateTime(utcNow(), 'MMM dd, yyyy')}
      - Body: @body('Parse_Digest')?['html']
      - Importance: Normal
      - Is HTML: Yes

6. If No:
   - Terminate: Success (no updates this week)
```

#### Code View (JSON):

```json
{
    "definition": {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.0.0.0",
        "triggers": {
            "Recurrence": {
                "type": "Recurrence",
                "recurrence": {
                    "frequency": "Week",
                    "interval": 1,
                    "schedule": {
                        "hours": ["9"],
                        "weekDays": ["Friday"]
                    },
                    "timeZone": "Eastern Standard Time"
                }
            }
        },
        "actions": {
            "Detect_Changes": {
                "type": "Http",
                "inputs": {
                    "method": "GET",
                    "uri": "https://cip-digest-functions.azurewebsites.net/api/detect-changes?space_key=CIPPMOPF&days=7"
                }
            },
            "Parse_Changes": {
                "type": "ParseJson",
                "inputs": {
                    "content": "@body('Detect_Changes')",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "new_pages": {"type": "array"},
                            "updated_pages": {"type": "array"},
                            "summary": {"type": "object"}
                        }
                    }
                },
                "runAfter": {
                    "Detect_Changes": ["Succeeded"]
                }
            },
            "Check_Updates": {
                "type": "If",
                "expression": {
                    "and": [{
                        "greater": [
                            "@add(body('Parse_Changes')?['summary']?['total_new'], body('Parse_Changes')?['summary']?['total_updated'])",
                            0
                        ]
                    }]
                },
                "actions": {
                    "Generate_Digest": {
                        "type": "Http",
                        "inputs": {
                            "method": "POST",
                            "uri": "https://cip-digest-functions.azurewebsites.net/api/generate-digest",
                            "headers": {
                                "Content-Type": "application/json"
                            },
                            "body": "@body('Parse_Changes')"
                        }
                    },
                    "Parse_Digest": {
                        "type": "ParseJson",
                        "inputs": {
                            "content": "@body('Generate_Digest')"
                        },
                        "runAfter": {
                            "Generate_Digest": ["Succeeded"]
                        }
                    },
                    "Send_Email": {
                        "type": "ApiConnection",
                        "inputs": {
                            "host": {
                                "connection": {
                                    "name": "@parameters('$connections')['office365']['connectionId']"
                                }
                            },
                            "method": "post",
                            "path": "/v2/Mail",
                            "body": {
                                "To": "your-team@eaton.com",
                                "Subject": "Weekly Confluence Digest - @{formatDateTime(utcNow(), 'MMM dd, yyyy')}",
                                "Body": "@body('Parse_Digest')?['html']",
                                "Importance": "Normal",
                                "IsHtml": true
                            }
                        },
                        "runAfter": {
                            "Parse_Digest": ["Succeeded"]
                        }
                    }
                },
                "runAfter": {
                    "Parse_Changes": ["Succeeded"]
                }
            }
        }
    }
}
```

## Alternative: Simpler Logic App (No Functions)

If you want to avoid Azure Functions, you can:

1. **Use Container Instance** - Package entire Python app in Docker container
2. **HTTP endpoint** - Host Python scripts on a VM/App Service with Flask/FastAPI

### Container Approach

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

# Main script that runs everything
CMD ["python", "run_weekly_digest.py"]
```

Logic App triggers container, waits for completion, reads results from blob storage.

## Configuration

Add these to Logic App **Application Settings**:

```
CONFLUENCE_URL=https://eaton-corp.atlassian.net/wiki
CONFLUENCE_EMAIL=shantanurbhute@eaton.com
CONFLUENCE_API_TOKEN=<your-token>
AZURE_OPENAI_ENDPOINT=<endpoint>
AZURE_OPENAI_API_KEY=<key>
BLOB_STORAGE_CONNECTION_STRING=<connection-string>
```

## Cost Estimate

**Azure Functions approach:**
- Logic App: ~$0.10/run (2 HTTP actions + email) × 52 weeks = ~$5.20/year
- Azure Functions: First 1M executions free = $0/year
- Storage: ~$0.50/year
- **Total: ~$6/year**

**Container Instance approach:**
- Logic App: ~$0.05/run × 52 = ~$2.60/year
- Container Instances: ~$0.05/run × 52 = ~$2.60/year
- **Total: ~$5/year**

## Testing

1. Test functions individually:
```bash
curl "https://cip-digest-functions.azurewebsites.net/api/detect-changes?space_key=CIPPMOPF&days=7"
```

2. Test Logic App with "Run Trigger" in Azure Portal

3. Monitor runs in Logic App → Runs history

## Troubleshooting

- **SSL Errors**: Add `verify=False` to all HTTPS calls (already done in scripts)
- **Timeout**: Increase Function timeout in `host.json` to 10 minutes
- **Memory**: Use Premium Function plan if processing large pages
- **Email Blocked**: Whitelist Logic App IP in corporate firewall

## Next Steps

1. Create Azure Function App
2. Deploy Python functions with dependencies
3. Create Logic App and connect Office 365
4. Test with manual trigger
5. Enable weekly schedule
