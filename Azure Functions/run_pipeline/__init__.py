"""
Manual Pipeline Trigger - HTTP Triggered Azure Function
Allows manual execution of the pipeline via HTTP POST
"""

import os
import sys
import json
import logging
import azure.functions as func
from datetime import datetime

# Add parent directory to path to import pipeline modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the main orchestrator logic
from pipeline_orchestrator import get_pages_config, process_single_page

# Import email generator and sender
from email_digest_generator import generate_page_summary_email
from email_sender import notify_subscribers_for_page

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP-triggered function for manual pipeline execution.
    
    Usage:
        POST /api/run_pipeline
        POST /api/run_pipeline?force=true  (force reprocessing)
        POST /api/run_pipeline?force_email=true  (force email even without changes)
        POST /api/run_pipeline?page_id=123456  (single page)
    """
    logger.info('Manual pipeline trigger received')
    
    try:
        # Parse parameters
        force = req.params.get('force', 'false').lower() == 'true'
        force_email = req.params.get('force_email', 'false').lower() == 'true'
        single_page_id = req.params.get('page_id')
        
        # Get pages to process
        pages = get_pages_config()
        
        if single_page_id:
            # Filter to single page
            pages = [p for p in pages if p['page_id'] == single_page_id]
            if not pages:
                return func.HttpResponse(
                    json.dumps({"error": f"Page {single_page_id} not found in config"}),
                    status_code=404,
                    mimetype="application/json"
                )
        
        if not pages:
            return func.HttpResponse(
                json.dumps({"error": "No pages configured. Set PAGE_IDS environment variable."}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Process pages
        results = []
        pages_changed = []
        
        for page in pages:
            logger.info(f"Processing page: {page['page_id']}")
            page_result = process_single_page(page, force_reprocess=force)
            results.append(page_result)
            
            if page_result['has_changes']:
                pages_changed.append(page_result['page_id'])
        
        # Generate emails and send to subscribers
        email_files = []
        emails_sent = 0
        for page_result in results:
            try:
                # Only generate email if changes OR force_email
                should_send = page_result['has_changes'] or force_email
                
                if not should_send:
                    logger.info(f"No changes for {page_result['page_id']} - skipping email (use force_email=true to override)")
                    continue
                
                logger.info(f"Generating email for {page_result['page_id']}...")
                email_result = generate_page_summary_email(
                    page_id=page_result['page_id'],
                    page_title=page_result['page_title'],
                    version=page_result['version'],
                    has_changes=page_result['has_changes'],
                    change_summary=page_result.get('change_summary', 'No changes'),
                    previous_version=page_result.get('previous_version')
                )
                if email_result:
                    email_files.append(email_result.get('html_file', 'unknown'))
                    
                    # Send email to subscribers
                    html_content = email_result.get('html_content', '')
                    if html_content:
                        logger.info(f"Sending email to subscribers for {page_result['page_id']}...")
                        space_key = page_result.get('space_key', 'CIPPMOPF')
                        send_result = notify_subscribers_for_page(
                            page_id=page_result['page_id'],
                            email_subject=f"📄 Updates for {page_result['page_title']} from {space_key}",
                            email_body=html_content
                        )
                        emails_sent += send_result.get('sent_count', 0)
                        logger.info(f"Sent {send_result.get('sent_count', 0)} emails for {page_result['page_id']}")
            except Exception as e:
                logger.error(f"Email generation/sending failed for {page_result['page_id']}: {e}")
        
        # Build response
        response = {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "pages_processed": len(results),
            "pages_changed": len(pages_changed),
            "changed_page_ids": pages_changed,
            "email_files": email_files,
            "emails_sent": emails_sent,
            "force_reprocess": force,
            "force_email": force_email,
            "results": results
        }
        
        return func.HttpResponse(
            json.dumps(response, indent=2),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
