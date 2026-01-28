"""
Email Sender Service
Sends digest emails to subscribers via Azure Logic App
"""

import os
import json
import requests
import urllib3
from datetime import datetime
from dotenv import load_dotenv

# Disable SSL warnings for corporate proxy
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

# Logic App configuration
LOGIC_APP_EMAIL_URL = os.getenv("LOGIC_APP_EMAIL_URL")

# Blob storage for email content
BLOB_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
EMAIL_CONTAINER = os.getenv("EMAIL_CONTAINER", "confluence-emails")


def get_blob_service_client():
    """Get blob service client with SSL verification disabled for corporate proxy"""
    from azure.storage.blob import BlobServiceClient
    from azure.core.pipeline.transport import RequestsTransport
    
    blob_account_key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
    
    # Create a session that doesn't verify SSL
    session = requests.Session()
    session.verify = False
    
    return BlobServiceClient(
        account_url=f"https://{BLOB_ACCOUNT_NAME}.blob.core.windows.net",
        credential=blob_account_key,
        transport=RequestsTransport(session=session),
        retry_total=1,
        retry_connect=1,
        retry_read=1
    )


def send_email_via_logic_app(to_email: str, subject: str, html_body: str, max_retries: int = 3) -> dict:
    """
    Send an email via Azure Logic App with retry logic.
    
    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_body: HTML content of the email
        max_retries: Maximum number of retry attempts
        
    Returns:
        dict with status and message
    """
    import time
    
    if not LOGIC_APP_EMAIL_URL:
        return {
            "status": "error",
            "message": "LOGIC_APP_EMAIL_URL not configured in environment"
        }
    
    payload = {
        "to": to_email,
        "subject": subject,
        "body": html_body
    }
    
    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.post(
                LOGIC_APP_EMAIL_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code in [200, 202]:
                return {
                    "status": "success",
                    "message": f"Email sent to {to_email}",
                    "response_code": response.status_code,
                    "attempts": attempt + 1
                }
            elif response.status_code >= 500:
                # Server error - retry
                last_error = f"Logic App returned {response.status_code}: {response.text}"
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    continue
            else:
                # Client error - don't retry
                return {
                    "status": "error",
                    "message": f"Logic App returned {response.status_code}: {response.text}",
                    "response_code": response.status_code
                }
                
        except requests.exceptions.Timeout:
            last_error = "Logic App request timed out"
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
        except Exception as e:
            last_error = f"Failed to send email: {str(e)}"
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
    
    return {
        "status": "error",
        "message": last_error,
        "attempts": max_retries
    }


def send_digest_to_subscribers(page_id: str, page_title: str, html_content: str, version: int) -> dict:
    """
    Send digest email to all subscribers of a page.
    
    Args:
        page_id: The Confluence page ID
        page_title: Title of the page
        html_content: The HTML email content
        version: The version number
        
    Returns:
        dict with results summary
    """
    try:
        from subscription_manager import get_subscribers_for_page
        
        subscribers = get_subscribers_for_page(page_id)
        
        if not subscribers:
            return {
                "status": "no_subscribers",
                "message": f"No subscribers for page {page_id}",
                "sent_count": 0,
                "failed_count": 0
            }
        
        # Build email subject
        subject = f"📄 Confluence Update: {page_title}"
        
        results = {
            "sent": [],
            "failed": [],
            "total": len(subscribers)
        }
        
        for subscriber in subscribers:
            email = subscriber.get('email')
            display_name = subscriber.get('displayName', email)
            
            print(f"   📧 Sending to {email}...")
            
            result = send_email_via_logic_app(
                to_email=email,
                subject=subject,
                html_body=html_content
            )
            
            if result['status'] == 'success':
                results['sent'].append(email)
                print(f"   ✅ Sent to {email}")
            else:
                results['failed'].append({
                    "email": email,
                    "error": result['message']
                })
                print(f"   ❌ Failed: {email} - {result['message']}")
        
        return {
            "status": "completed",
            "message": f"Sent {len(results['sent'])}/{results['total']} emails",
            "sent_count": len(results['sent']),
            "failed_count": len(results['failed']),
            "sent_to": results['sent'],
            "failed": results['failed']
        }
        
    except ImportError:
        return {
            "status": "error",
            "message": "subscription_manager not available - Cosmos DB not configured"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error sending digests: {str(e)}"
        }


def get_email_from_blob(page_id: str) -> str:
    """
    Get the latest email HTML content from Blob Storage.
    
    Args:
        page_id: The page ID
        
    Returns:
        HTML content string or None
    """
    try:
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(EMAIL_CONTAINER)
        blob_client = container_client.get_blob_client(f"{page_id}/latest/digest.html")
        
        download = blob_client.download_blob(timeout=10)
        html_content = download.readall().decode('utf-8')
        
        return html_content
        
    except Exception as e:
        print(f"⚠️ Could not get email from blob (non-blocking): {str(e)[:50]}")
        return None


def get_email_metadata_from_blob(page_id: str) -> dict:
    """
    Get the email metadata from Blob Storage.
    
    Args:
        page_id: The page ID
        
    Returns:
        Metadata dict or None
    """
    try:
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(EMAIL_CONTAINER)
        blob_client = container_client.get_blob_client(f"{page_id}/latest/metadata.json")
        
        download = blob_client.download_blob(timeout=10)
        metadata = json.loads(download.readall().decode('utf-8'))
        
        return metadata
        
    except Exception as e:
        print(f"⚠️ Could not get metadata from blob (non-blocking): {str(e)[:50]}")
        return None


def notify_subscribers_for_page(page_id: str, email_subject: str = None, email_body: str = None) -> dict:
    """
    Main function to notify all subscribers when a page is updated.
    Can use provided email content or get from blob storage.
    
    Args:
        page_id: The page ID that was updated
        email_subject: Optional email subject (if not provided, auto-generated)
        email_body: Optional HTML content (if not provided, fetched from blob)
        
    Returns:
        dict with results
    """
    print(f"\n📬 Notifying subscribers for page {page_id}...")
    
    # Use provided content or get from blob
    html_content = email_body
    if not html_content:
        html_content = get_email_from_blob(page_id)
        
    if not html_content:
        return {
            "status": "error",
            "message": f"No email content found for page {page_id}"
        }
    
    # Get metadata for title/version if not provided in subject
    metadata = get_email_metadata_from_blob(page_id)
    if not metadata:
        metadata = {"page_title": f"Page {page_id}", "version": 1}
    
    # Use provided subject or generate one
    subject = email_subject
    if not subject:
        subject = f"📄 Update: {metadata.get('page_title', f'Page {page_id}')} (v{metadata.get('version', 1)})"
    
    # Get subscribers for this page
    try:
        from subscription_manager import get_subscribers_for_page
        subscribers = get_subscribers_for_page(page_id)
    except Exception as e:
        print(f"   ⚠️  Could not get subscribers: {e}")
        return {
            "status": "error",
            "message": f"Failed to get subscribers: {str(e)}"
        }
    
    if not subscribers:
        print(f"   ℹ️  No subscribers for page {page_id}")
        return {
            "status": "success",
            "message": "No subscribers for this page",
            "sent_count": 0
        }
    
    print(f"   📧 Found {len(subscribers)} subscriber(s)")
    
    # Send to each subscriber
    sent_count = 0
    failed_count = 0
    results = []
    
    for subscriber in subscribers:
        email = subscriber.get('email')
        name = subscriber.get('displayName', email)
        
        print(f"   📤 Sending to {name} ({email})...")
        
        result = send_email_via_logic_app(
            to_email=email,
            subject=subject,
            html_body=html_content
        )
        
        results.append({
            "email": email,
            "status": result.get('status'),
            "message": result.get('message')
        })
        
        if result.get('status') == 'success':
            sent_count += 1
            print(f"      ✅ Sent!")
        else:
            failed_count += 1
            print(f"      ❌ Failed: {result.get('message')}")
    
    return {
        "status": "success" if sent_count > 0 else "error",
        "message": f"Sent {sent_count}/{len(subscribers)} emails",
        "sent_count": sent_count,
        "failed_count": failed_count,
        "details": results
    }


# ===== Test Functions =====
if __name__ == "__main__":
    print("Email Sender Service Test")
    print("=" * 50)
    
    # Check if Logic App is configured
    if LOGIC_APP_EMAIL_URL:
        print("✅ Logic App URL configured")
    else:
        print("⚠️  Logic App URL not configured")
        print("   Add LOGIC_APP_EMAIL_URL to your .env file")
    
    # Test sending a sample email
    if LOGIC_APP_EMAIL_URL:
        print("\nSending test email...")
        result = send_email_via_logic_app(
            to_email="test@example.com",
            subject="Test Email from CIP Digest",
            html_body="<h1>Test</h1><p>This is a test email.</p>"
        )
        print(f"Result: {result}")
    
    # Test getting email from blob
    print("\nTesting blob retrieval...")
    html = get_email_from_blob("164168599")
    if html:
        print(f"✅ Found email in blob ({len(html)} chars)")
    else:
        print("⚠️  No email found in blob (may not be uploaded yet)")
