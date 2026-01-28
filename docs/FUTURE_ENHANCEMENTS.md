# Future Enhancements Roadmap

## 1. User Authentication & Subscription Management

### Microsoft SSO Authentication
```python
# auth/microsoft_sso.py
from msal import ConfidentialClientApplication
import os

def get_auth_url():
    """Generate Microsoft SSO login URL"""
    app = ConfidentialClientApplication(
        os.getenv("AZURE_CLIENT_ID"),
        authority=f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID')}",
        client_credential=os.getenv("AZURE_CLIENT_SECRET")
    )
    
    auth_url = app.get_authorization_request_url(
        scopes=["User.Read"],
        redirect_uri=os.getenv("REDIRECT_URI")
    )
    return auth_url

def verify_token(code):
    """Verify SSO token and get user info"""
    app = ConfidentialClientApplication(...)
    result = app.acquire_token_by_authorization_code(
        code,
        scopes=["User.Read"],
        redirect_uri=os.getenv("REDIRECT_URI")
    )
    return result
```

### Subscription Database Schema
```sql
-- Azure SQL or Cosmos DB
CREATE TABLE users (
    user_id VARCHAR(100) PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    created_at DATETIME DEFAULT GETDATE()
);

CREATE TABLE subscriptions (
    subscription_id INT IDENTITY(1,1) PRIMARY KEY,
    user_id VARCHAR(100) FOREIGN KEY REFERENCES users(user_id),
    subscription_type VARCHAR(20), -- 'page' or 'space'
    page_id VARCHAR(50),
    space_key VARCHAR(50),
    created_at DATETIME DEFAULT GETDATE()
);

CREATE TABLE user_preferences (
    user_id VARCHAR(100) PRIMARY KEY,
    frequency VARCHAR(20) DEFAULT 'daily', -- 'realtime', 'daily', 'weekly'
    digest_format VARCHAR(20) DEFAULT 'detailed' -- 'detailed', 'summary'
);
```

### Subscription Manager
```python
# subscription_manager.py
class SubscriptionManager:
    def subscribe_to_page(self, user_id, page_id):
        """Subscribe user to a specific page"""
        pass
    
    def subscribe_to_space(self, user_id, space_key):
        """Subscribe user to all pages in a space"""
        pass
    
    def get_user_subscriptions(self, user_id):
        """Get all subscriptions for a user"""
        pass
    
    def get_subscribers_for_page(self, page_id):
        """Get all users subscribed to a page"""
        pass
    
    def get_subscribers_for_space(self, space_key):
        """Get all users subscribed to a space"""
        pass
```

## 2. Space-Level Aggregated Summaries

### Space Digest Generator
```python
# space_digest_generator.py
def generate_space_digest(space_key, since_date):
    """
    Generate aggregated digest for entire space
    
    Returns:
        - Summary of all page updates in the space
        - Grouped by category/page type
        - Timeline of changes
    """
    
    # 1. Get all pages in space that changed
    changed_pages = get_changed_pages_in_space(space_key, since_date)
    
    # 2. Retrieve indexed chunks for all pages
    all_chunks = []
    for page in changed_pages:
        chunks = retrieve_page_content(page['page_id'])
        all_chunks.extend(chunks)
    
    # 3. Agent 1: Space-level aggregator
    space_summary = agent_space_aggregator(space_key, changed_pages, all_chunks)
    
    # 4. Agent 2: HTML formatter
    html = format_space_digest_html(space_key, space_summary, changed_pages)
    
    return html
```

### Agent: Space Aggregator (GPT-4o)
```python
def agent_space_aggregator(space_key, changed_pages, all_chunks):
    """
    Multi-page aggregator agent
    
    Input: All chunks from multiple pages
    Output: Space-level executive summary
    """
    
    prompt = f"""
    You are summarizing updates across an entire Confluence space: {space_key}
    
    {len(changed_pages)} pages were updated:
    {[p['page_title'] for p in changed_pages]}
    
    Content from all pages:
    {all_chunks[:20000]}  # First 20K chars
    
    Create a SPACE-LEVEL DIGEST with:
    
    1. Overview (2-3 sentences about the space's purpose)
    
    2. Key Updates This Week:
       - Group by theme/category
       - Mention each page that changed
       - Highlight major changes
    
    3. Notable Changes:
       - New pages added
       - Significant content updates
       - New images/diagrams
    
    4. For Technical Teams:
       - Process updates
       - New tools/resources
       - Technical guidance changes
    
    5. For Managers:
       - Strategic updates
       - Policy changes
       - Governance updates
    """
    
    # Call GPT-4o
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=2000
    )
    
    return response.choices[0].message.content
```

## 3. Time-Based Triggers

### Azure Logic Apps / Functions
```python
# azure_function/timer_trigger/__init__.py
import azure.functions as func
from datetime import datetime

def main(mytimer: func.TimerRequest) -> None:
    """
    Timer trigger that runs daily at 8 AM UTC
    CRON: 0 0 8 * * *
    """
    
    print(f"Timer trigger fired at: {datetime.utcnow()}")
    
    # 1. Check all subscriptions
    active_subscriptions = get_active_subscriptions()
    
    # 2. Group by space/page
    pages_to_process = group_subscriptions_by_target(active_subscriptions)
    
    # 3. Run pipeline for each
    for page_id in pages_to_process['pages']:
        run_page_pipeline(page_id)
    
    for space_key in pages_to_process['spaces']:
        run_space_pipeline(space_key)
    
    # 4. Send emails to subscribers
    send_digest_emails(active_subscriptions)
```

### function.json
```json
{
  "scriptFile": "__init__.py",
  "bindings": [
    {
      "name": "mytimer",
      "type": "timerTrigger",
      "direction": "in",
      "schedule": "0 0 8 * * *"
    }
  ]
}
```

### Manual Trigger Endpoint
```python
# azure_function/http_trigger/__init__.py
import azure.functions as func

def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger for manual pipeline execution
    POST /api/trigger-pipeline
    Body: {"page_id": "123", "space_key": "CIP"}
    """
    
    page_id = req.params.get('page_id')
    space_key = req.params.get('space_key')
    
    if page_id:
        result = run_page_pipeline(page_id)
    elif space_key:
        result = run_space_pipeline(space_key)
    
    return func.HttpResponse(
        json.dumps(result),
        mimetype="application/json"
    )
```

## 4. Email Distribution

### Email Sender (Azure Communication Services)
```python
# email_sender.py
from azure.communication.email import EmailClient

def send_digest_to_subscribers(page_id, html_content):
    """Send digest email to all subscribers"""
    
    subscribers = get_subscribers_for_page(page_id)
    
    email_client = EmailClient.from_connection_string(
        os.getenv("COMMUNICATION_SERVICES_CONNECTION_STRING")
    )
    
    for user in subscribers:
        message = {
            "senderAddress": "noreply@cipdigest.com",
            "recipients": {
                "to": [{"address": user['email']}]
            },
            "content": {
                "subject": f"CIP Weekly Digest: {page_title}",
                "html": html_content
            }
        }
        
        poller = email_client.begin_send(message)
        result = poller.result()
```

## Implementation Timeline

### Phase 1: Authentication & Subscriptions (2-3 weeks)
- [ ] Setup Microsoft SSO
- [ ] Create subscription database
- [ ] Build subscription API endpoints
- [ ] Create simple web UI for subscription management

### Phase 2: Space-Level Digests (1-2 weeks)
- [ ] Implement space aggregator agent
- [ ] Create space digest HTML template
- [ ] Test with real data

### Phase 3: Timer Triggers (1 week)
- [ ] Deploy Azure Function with timer trigger
- [ ] Setup Logic Apps for orchestration
- [ ] Add manual trigger endpoint

### Phase 4: Email Distribution (1 week)
- [ ] Integrate Azure Communication Services
- [ ] Implement email queuing
- [ ] Add unsubscribe functionality

## Technology Stack

| Component | Technology |
|-----------|------------|
| Authentication | Microsoft SSO (MSAL) |
| Database | Azure SQL / Cosmos DB |
| Timer Triggers | Azure Functions / Logic Apps |
| Email Service | Azure Communication Services |
| Web UI | Flask/FastAPI + React |
| API | FastAPI REST endpoints |
