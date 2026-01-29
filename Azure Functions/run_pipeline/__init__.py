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
from pathlib import Path

# Add parent directory to path to import pipeline modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import pipeline modules directly
from single_page_monitor import detect_changes_optimized
from confluence_content_extractor import extract_and_save_page, get_data_folder
from image_description_generator import describe_images_in_document
from blob_storage_uploader import upload_page_to_blob
from azure_search_indexer import create_search_index, index_single_page
from email_digest_generator import generate_page_summary_email
from email_sender import notify_subscribers_for_page

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_pages_config():
    """Get configured pages from environment or config"""
    page_ids_str = os.getenv("PAGE_IDS", "")
    space_key = os.getenv("SPACE_KEY", "CIPPMOPF")
    
    if not page_ids_str:
        return []
    
    pages = []
    for page_id in page_ids_str.split(","):
        page_id = page_id.strip()
        if page_id:
            pages.append({
                "page_id": page_id,
                "space_key": space_key
            })
    return pages


def process_single_page(page_config: dict, force_reprocess: bool = False) -> dict:
    """Process a single page through the full pipeline"""
    page_id = page_config['page_id']
    space_key = page_config.get('space_key', 'CIPPMOPF')
    
    result = {
        'page_id': page_id,
        'space_key': space_key,
        'has_changes': False,
        'version': None,
        'page_title': f"Page {page_id}",
        'steps_completed': []
    }
    
    try:
        # Step 1: Check for changes
        logger.info(f"[{page_id}] Step 1: Checking for changes...")
        change_result = detect_changes_optimized(page_id)
        result['has_changes'] = change_result.get('has_changes', False) or force_reprocess
        result['version'] = change_result.get('version_number')  # Fixed: was 'current_version'
        result['previous_version'] = change_result.get('previous_version')
        # Fixed: detect_changes_optimized returns 'title', not 'page_title'
        result['page_title'] = change_result.get('title', f"Page {page_id}")
        # Store the detailed change summary from detection
        result['change_summary'] = change_result.get('change_summary', '')
        result['steps_completed'].append('change_detection')
        
        if not result['has_changes']:
            logger.info(f"[{page_id}] No changes detected, skipping processing")
            return result
        
        # Step 2: Extract content - extract_and_save_page auto-detects space from API
        logger.info(f"[{page_id}] Step 2: Extracting content...")
        extract_result = extract_and_save_page(page_id)
        result['steps_completed'].append('content_extraction')
        
        # Get the document folder path (uses /tmp in Azure Functions)
        data_folder = get_data_folder()
        doc_folder = data_folder / "pages" / space_key / page_id
        doc_json_path = doc_folder / "document.json"
        
        # Step 3: Process images
        logger.info(f"[{page_id}] Step 3: Processing images...")
        try:
            describe_images_in_document(str(doc_json_path))
            result['steps_completed'].append('image_processing')
        except Exception as e:
            logger.warning(f"[{page_id}] Image processing skipped: {e}")
        
        # Step 4: Upload to blob
        logger.info(f"[{page_id}] Step 4: Uploading to blob storage...")
        upload_page_to_blob(str(doc_folder))
        result['steps_completed'].append('blob_upload')
        
        # Step 5: Index for search
        logger.info(f"[{page_id}] Step 5: Indexing for search...")
        try:
            create_search_index()
            index_single_page(page_id, space_key)
            result['steps_completed'].append('search_indexing')
        except Exception as e:
            logger.warning(f"[{page_id}] Search indexing skipped: {e}")
        
        # Only set generic change summary if not already set from detection
        if not result.get('change_summary'):
            result['change_summary'] = f"Updated to version {result['version']}"
        logger.info(f"[{page_id}] Processing complete!")
        
    except Exception as e:
        logger.error(f"[{page_id}] Processing failed: {e}")
        result['error'] = str(e)
    
    return result


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
