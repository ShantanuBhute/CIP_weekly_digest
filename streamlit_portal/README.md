# CIP Digest Subscription Portal

Streamlit-based subscription management for Confluence page notifications.

## Deploy to Streamlit Community Cloud (FREE)

### 1. Push to GitHub
```bash
cd streamlit_portal
git init
git add .
git commit -m "Initial Streamlit app"
git remote add origin https://github.com/YOUR_USERNAME/cip-digest-portal.git
git push -u origin main
```

### 2. Deploy on Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "New app"
3. Select your GitHub repo
4. Set main file path: `app.py`
5. Click "Deploy"

### 3. Configure Secrets
In Streamlit Cloud dashboard, go to Settings > Secrets and add:

```toml
COSMOS_ENDPOINT = "https://cip-digest-cosmos.documents.azure.com:443/"
COSMOS_KEY = "your-cosmos-key"
COSMOS_DATABASE = "confluence-digest"
COSMOS_CONTAINER = "subscriptions"
```

## Local Development
```bash
pip install -r requirements.txt
streamlit run app.py
```
