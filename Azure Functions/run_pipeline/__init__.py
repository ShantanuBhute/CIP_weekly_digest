"""
Manual Pipeline Trigger - HTTP Triggered Azure Function
Allows manual execution of the pipeline via HTTP POST

V2 OPTIMIZED VERSION:
- Image caching (skip download if unchanged)
- Description caching (skip GPT-4o if image hash unchanged)
- Upload deduplication (skip upload if MD5 matches)
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

# V2 Pipeline (optimized with caching)
from v2_pipeline import V2Pipeline, run_v2_pipeline

# V1 modules still needed for email/search
from azure_search_indexer import create_search_index, index_page_from_local
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


def process_single_page_v2(page_config: dict, pipeline: V2Pipeline, force_reprocess: bool = False) -> dict:
    """
    Process a single page through the V2 OPTIMIZED pipeline.
    
    V2 Optimizations:
    - Image caching: Skip download if unchanged
    - Description caching: Skip GPT-4o if image hash unchanged  
    - Upload deduplication: Skip upload if MD5 matches
    """
    page_id = page_config['page_id']
    space_key = page_config.get('space_key', 'CIPPMOPF')
    
    logger.info(f"[{page_id}] Starting V2 pipeline processing...")
    
    # Use V2 pipeline
    result = pipeline.process_page(page_id, force=force_reprocess)
    
    # Add space_key to result
    result['space_key'] = space_key
    
    return result


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP-triggered function for manual pipeline execution.
    
    V2 OPTIMIZED VERSION with caching!
    
    Usage:
        POST /api/run_pipeline
        POST /api/run_pipeline?force=true  (force reprocessing)
        POST /api/run_pipeline?force_email=true  (force email even without changes)
        POST /api/run_pipeline?page_id=123456  (single page)
    """
    logger.info('Manual pipeline trigger received (V2 OPTIMIZED)')
    
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
        
        # Initialize V2 Pipeline (with caching)
        pipeline = V2Pipeline()
        logger.info("V2 Pipeline initialized with caching enabled")
        
        # Ensure search index exists
        try:
            create_search_index()
            logger.info("Search index ready")
        except Exception as e:
            logger.warning(f"Search index creation warning (may already exist): {e}")
        
        # Process pages using V2 pipeline
        results = []
        pages_changed = []
        
        for page in pages:
            logger.info(f"Processing page: {page['page_id']} with V2 pipeline")
            page_result = process_single_page_v2(page, pipeline, force_reprocess=force)
            results.append(page_result)
            
            if page_result.get('has_changes'):
                pages_changed.append(page_result['page_id'])
                
                # INDEX TO SEARCH after V2 pipeline extracts content
                # This ensures email generator gets FRESH data from search index
                try:
                    logger.info(f"Indexing page {page_result['page_id']} to Azure AI Search...")
                    doc_path = page_result.get('document_path')
                    if doc_path:
                        index_page_from_local(
                            page_id=page_result['page_id'],
                            document_json_path=doc_path
                        )
                        logger.info(f"✅ Page {page_result['page_id']} indexed to search")
                    else:
                        logger.warning(f"No document_path for {page_result['page_id']}, skipping search index")
                except Exception as e:
                    logger.error(f"Search indexing failed for {page_result['page_id']}: {e}")
        
        # Log V2 optimization stats
        logger.info("=" * 60)
        logger.info("V2 OPTIMIZATION STATS:")
        logger.info(f"  Images downloaded: {pipeline.stats['images_downloaded']}")
        logger.info(f"  Images from cache: {pipeline.stats['images_cached']}")
        logger.info(f"  Descriptions generated: {pipeline.stats['descriptions_generated']}")
        logger.info(f"  Descriptions from cache: {pipeline.stats['descriptions_cached']}")
        logger.info(f"  Cost saved: ${pipeline.stats['estimated_cost_saved']:.2f}")
        logger.info("=" * 60)
        
        # Generate emails and send to subscribers
        email_files = []
        emails_sent = 0
        for page_result in results:
            try:
                # Only generate email if changes OR force_email
                should_send = page_result.get('has_changes') or force_email
                
                if not should_send:
                    logger.info(f"No changes for {page_result['page_id']} - skipping email")
                    continue
                
                logger.info(f"Generating email for {page_result['page_id']}...")
                email_result = generate_page_summary_email(
                    page_id=page_result['page_id'],
                    page_title=page_result.get('title', f"Page {page_result['page_id']}"),
                    version=page_result.get('version'),
                    has_changes=page_result.get('has_changes'),
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
                            email_subject=f"Updates for {page_result.get('title', 'Page')} from {space_key}",
                            email_body=html_content
                        )
                        emails_sent += send_result.get('sent_count', 0)
                        logger.info(f"Sent {send_result.get('sent_count', 0)} emails")
            except Exception as e:
                logger.error(f"Email generation/sending failed for {page_result['page_id']}: {e}")
        
        # Build response with V2 stats
        response = {
            "status": "success",
            "version": "V2_OPTIMIZED",
            "timestamp": datetime.utcnow().isoformat(),
            "pages_processed": len(results),
            "pages_changed": len(pages_changed),
            "changed_page_ids": pages_changed,
            "v2_optimization_stats": {
                "images_downloaded": pipeline.stats['images_downloaded'],
                "images_from_cache": pipeline.stats['images_cached'],
                "descriptions_generated": pipeline.stats['descriptions_generated'],
                "descriptions_from_cache": pipeline.stats['descriptions_cached'],
                "estimated_cost_saved": f"${pipeline.stats['estimated_cost_saved']:.2f}"
            },
            "email_files": email_files,
            "emails_sent": emails_sent,
            "force_reprocess": force,
            "force_email": force_email,
            "results": results
        }
        
        return func.HttpResponse(
            json.dumps(response, indent=2, default=str),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        import traceback
        return func.HttpResponse(
            json.dumps({"error": str(e), "traceback": traceback.format_exc()}),
            status_code=500,
            mimetype="application/json"
        )
