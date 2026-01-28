"""
Pipeline Orchestrator - Timer Triggered Azure Function
Runs every 10 minutes to check for Confluence changes and process updates
"""

import os
import sys
import json
import logging
import azure.functions as func
from datetime import datetime

# Add parent directory to path to import pipeline modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import pipeline modules (same code as root)
from single_page_monitor import detect_changes_optimized
from confluence_content_extractor import extract_and_save_page
from image_description_generator import describe_images_in_document
from blob_storage_uploader import upload_page_to_blob
from azure_search_indexer import create_search_index, index_single_page
from email_digest_generator import generate_page_summary_email
from email_sender import notify_subscribers_for_page

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_pages_config():
    """Get pages to monitor from environment variables"""
    page_ids = os.getenv("PAGE_IDS", "").split(",")
    space_key = os.getenv("SPACE_KEY", "CIPPMOPF")
    
    pages = []
    for pid in page_ids:
        pid = pid.strip()
        if pid:
            pages.append({
                "page_id": pid,
                "title": f"Page {pid}",  # Title will be updated from Confluence
                "space_key": space_key
            })
    return pages


def process_single_page(page, force_reprocess=False):
    """
    Process a single page through the complete pipeline.
    
    Steps:
    1. Detect changes
    2. Extract content (if changed)
    3. Describe images (if changed)
    4. Upload to blob (if changed)
    5. Index in search (if changed)
    6. Generate email
    """
    page_id = page['page_id']
    page_title = page['title']
    space_key = page['space_key']
    
    result = {
        'page_id': page_id,
        'page_title': page_title,
        'space_key': space_key,
        'status': 'unknown',
        'has_changes': False,
        'version': 0,
        'steps_completed': [],
        'errors': []
    }
    
    try:
        # Step 1: Detect changes
        logger.info(f"Step 1: Detecting changes for {page_id}")
        change_result = detect_changes_optimized(page_id)
        result['has_changes'] = change_result['has_changes']
        result['version'] = change_result['version_number']
        result['change_summary'] = change_result['change_summary']
        result['previous_version'] = change_result.get('previous_version')
        result['page_title'] = change_result.get('title', page_title)
        result['steps_completed'].append('detect_changes')
        
        need_full_pipeline = change_result['needs_reprocessing'] or force_reprocess
        
        if need_full_pipeline:
            logger.info(f"Changes detected for {page_id} - running full pipeline")
            
            # Step 2: Extract content
            logger.info(f"Step 2: Extracting content for {page_id}")
            document = extract_and_save_page(page_id)
            if document:
                result['steps_completed'].append('extract_content')
            else:
                result['errors'].append('extract_content')
            
            # Step 3: Describe images
            logger.info(f"Step 3: Describing images for {page_id}")
            doc_path = f"data/pages/{space_key}/{page_id}/document.json"
            if os.path.exists(doc_path):
                img_result = describe_images_in_document(doc_path)
                if img_result:
                    result['steps_completed'].append('describe_images')
                else:
                    result['errors'].append('describe_images')
            
            # Step 4: Upload to blob
            logger.info(f"Step 4: Uploading to blob for {page_id}")
            doc_folder = f"data/pages/{space_key}/{page_id}"
            upload_result = upload_page_to_blob(doc_folder)
            if upload_result.get('success'):
                result['steps_completed'].append('upload_blob')
            else:
                result['errors'].append('upload_blob')
            
            # Step 5: Index in search
            logger.info(f"Step 5: Indexing in search for {page_id}")
            create_search_index()
            chunks = index_single_page(page_id, space_key, delete_existing=True)
            if chunks > 0:
                result['steps_completed'].append('index_search')
            else:
                result['errors'].append('index_search')
        
        else:
            logger.info(f"No changes for {page_id} - skipping content processing")
        
        # Set final status
        result['status'] = 'success' if not result['errors'] else 'partial_success'
        
    except Exception as e:
        logger.error(f"Error processing page {page_id}: {e}")
        result['status'] = 'error'
        result['errors'].append(str(e))
    
    return result


def main(timer: func.TimerRequest) -> None:
    """
    Timer-triggered function that runs the complete pipeline.
    Executes every 10 minutes (configurable in function.json).
    """
    utc_timestamp = datetime.utcnow().isoformat()
    
    if timer.past_due:
        logger.warning('Timer is past due!')
    
    logger.info(f'Pipeline orchestrator started at {utc_timestamp}')
    
    try:
        # Get pages to monitor
        pages = get_pages_config()
        logger.info(f"Monitoring {len(pages)} pages")
        
        if not pages:
            logger.warning("No pages configured. Set PAGE_IDS environment variable.")
            return
        
        # Process each page
        results = []
        pages_changed = []
        
        for page in pages:
            logger.info(f"Processing page: {page['page_id']}")
            page_result = process_single_page(page)
            results.append(page_result)
            
            if page_result['has_changes']:
                pages_changed.append(page_result['page_id'])
        
        # Step 6: Generate emails for pages with changes and send to subscribers
        logger.info("Step 6: Generating email digests")
        for page_result in results:
            try:
                # Only generate and send emails for pages that changed
                if not page_result['has_changes']:
                    logger.info(f"No changes for {page_result['page_id']} - skipping email")
                    continue
                
                # Generate email (this makes GPT-4 calls - can be slow)
                logger.info(f"Generating email for {page_result['page_id']}...")
                email_result = generate_page_summary_email(
                    page_id=page_result['page_id'],
                    page_title=page_result['page_title'],
                    version=page_result['version'],
                    has_changes=page_result['has_changes'],
                    change_summary=page_result.get('change_summary', 'No changes'),
                    previous_version=page_result.get('previous_version')
                )
                
                if not email_result:
                    logger.warning(f"No email generated for {page_result['page_id']}")
                    continue
                    
                logger.info(f"Email generated: {email_result.get('html_file', 'unknown')}")
                
                # Step 7: Send email to subscribers
                logger.info(f"Step 7: Sending email to subscribers for {page_result['page_id']}")
                html_content = email_result.get('html_content', '')
                if html_content:
                    space_key = page_result.get('space_key', 'CIPPMOPF')
                    send_result = notify_subscribers_for_page(
                        page_id=page_result['page_id'],
                        email_subject=f"📄 Updates for {page_result['page_title']} from {space_key}",
                        email_body=html_content
                    )
                    logger.info(f"Email sent to {send_result.get('sent_count', 0)} subscribers")
                else:
                    logger.warning(f"No HTML content for {page_result['page_id']}")
                    
            except Exception as e:
                logger.error(f"Email generation/sending failed for {page_result['page_id']}: {e}")
                # Continue to next page instead of failing completely
                continue
        
        # Summary
        logger.info(f"Pipeline completed. Processed {len(results)} pages, {len(pages_changed)} with changes.")
        
    except Exception as e:
        logger.error(f"Pipeline orchestrator failed: {e}")
        raise
