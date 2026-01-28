"""
==============================================================================
CONFLUENCE WEEKLY DIGEST - MAIN ORCHESTRATOR
==============================================================================

This is the SINGLE entry point for the entire pipeline.
Run this script to execute the complete workflow.

Pages monitored are defined in: pages_config.py

WORKFLOW:
=========

    +-------------------+
    |   START           |
    +-------------------+
            |
            v
    +-------------------+
    | LOAD CONFIG       |  <-- pages_config.py
    | - Get pages list  |
    +-------------------+
            |
            v
    +-------------------+
    | FOR EACH PAGE:    |
    +-------------------+
            |
            v
    +-------------------+
    | 1. DETECT CHANGES |  <-- single_page_monitor.py
    | - Extract raw text|
    | - Compare hashes  |
    +-------------------+
            |
            v
       +---------+
       | Changed?|
       +---------+
        /      \
      NO        YES
      /          \
     v            v
    +----------+  +----------------------+
    | Skip     |  | 2. EXTRACT CONTENT   |  <-- confluence_content_extractor.py
    | Pipeline |  | - Parse HTML blocks  |
    +----------+  | - Download images    |
     |            +----------------------+
     |                      |
     |                      v
     |            +----------------------+
     |            | 3. DESCRIBE IMAGES   |  <-- image_description_generator.py
     |            | - GPT-4o Vision API  |
     |            | - Generate captions  |
     |            +----------------------+
     |                      |
     |                      v
     |            +----------------------+
     |            | 4. UPLOAD TO BLOB    |  <-- blob_storage_uploader.py
     |            | - confluence-media   |
     |            | - confluence-rag     |
     |            +----------------------+
     |                      |
     |                      v
     |            +----------------------+
     |            | 5. DELETE OLD CHUNKS |  <-- azure_search_indexer.py
     |            | - Remove from index  |
     |            +----------------------+
     |                      |
     |                      v
     |            +----------------------+
     |            | 6. INDEX IN SEARCH   |  <-- azure_search_indexer.py
     |            | - Generate embeddings|
     |            | - Upload chunks      |
     |            +----------------------+
     |                      |
     +----------+-----------+
                |
                v
    +------------------------+
    | 7. GENERATE EMAIL      |  <-- email_digest_generator.py
    | - Retrieve from index  |
    | - GPT-4o RAG summary   |
    | - Format HTML email    |
    +------------------------+
                |
                v
    +-------------------+
    |   OUTPUT:         |
    | - HTML Email      |
    | - JSON Metadata   |
    +-------------------+
                |
                v
    +-------------------+
    |   END             |
    +-------------------+


USAGE:
======
    python main.py                    # Run complete workflow
    python main.py --force            # Force reprocessing even if no changes
    python main.py --email-only       # Only generate email (skip extraction)


COST OPTIMIZATION:
==================
    - If NO changes: ~$0.01 (just email generation)
    - If changes: ~$0.05 per page (full pipeline + email)
    - Weekly cost estimate: ~$1/year

==============================================================================
"""

import os
import sys
import json
import argparse
from datetime import datetime

# Fix Windows console encoding for Unicode/emojis
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Pipeline modules
from pages_config import get_pages_to_monitor, SPACE_KEY
from single_page_monitor import detect_changes_optimized
from confluence_content_extractor import extract_and_save_page
from image_description_generator import describe_images_in_document
from blob_storage_uploader import upload_page_to_blob
from azure_search_indexer import create_search_index, index_single_page, delete_page_chunks
from email_digest_generator import generate_page_summary_email


def print_banner(pages):
    """Print startup banner"""
    print("\n")
    print("=" * 70)
    print("   CONFLUENCE WEEKLY DIGEST PIPELINE")
    print("=" * 70)
    print(f"   Monitoring {len(pages)} page(s):")
    for p in pages:
        print(f"     - {p['title']} (ID: {p['page_id']})")
    print(f"   Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 70)


def step_1_detect_changes(page_id, page_title):
    """Step 1: Detect if page content has changed"""
    print("\n")
    print("-" * 70)
    print(f"STEP 1: DETECTING CHANGES - {page_title}")
    print("-" * 70)
    
    result = detect_changes_optimized(page_id)
    return result


def step_2_extract_content(page_id, page_title, space_key):
    """Step 2: Extract content with images from Confluence"""
    print("\n")
    print("-" * 70)
    print(f"STEP 2: EXTRACTING CONTENT - {page_title}")
    print("-" * 70)
    
    document = extract_and_save_page(page_id)
    
    if document:
        print(f"   [OK] Extracted {len(document['content_blocks'])} content blocks")
        return True
    else:
        print("   [ERROR] Content extraction failed")
        return False


def step_3_describe_images(page_id, page_title, space_key):
    """Step 3: Generate AI descriptions for images using GPT-4o Vision"""
    print("\n")
    print("-" * 70)
    print(f"STEP 3: DESCRIBING IMAGES - {page_title}")
    print("-" * 70)
    
    doc_path = f"data/pages/{space_key}/{page_id}/document.json"
    
    if not os.path.exists(doc_path):
        print(f"   [ERROR] Document not found: {doc_path}")
        return False
    
    result = describe_images_in_document(doc_path)
    
    if result:
        image_count = result.get('images_processed', 0)
        print(f"   [OK] Described {image_count} images")
        return True
    else:
        print("   [ERROR] Image description failed")
        return False


def step_4_upload_to_blob(page_id, page_title, space_key, version):
    """Step 4: Upload document and images to Azure Blob Storage"""
    print("\n")
    print("-" * 70)
    print(f"STEP 4: UPLOADING TO BLOB STORAGE - {page_title}")
    print("-" * 70)
    
    try:
        doc_folder = f"data/pages/{space_key}/{page_id}"
        result = upload_page_to_blob(doc_folder)
        
        if result.get('success'):
            print(f"   [OK] Uploaded to blob storage")
            if result.get('rag_blob_url'):
                print(f"   URL: {result['rag_blob_url']}")
            return True
        else:
            print(f"   [ERROR] Upload failed: {result.get('error', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"   [ERROR] Upload failed: {e}")
        return False


def step_5_index_in_search(page_id, page_title, space_key):
    """Step 5: Index content in Azure AI Search with embeddings (deletes old chunks first)"""
    print("\n")
    print("-" * 70)
    print(f"STEP 5: INDEXING IN AZURE AI SEARCH - {page_title}")
    print("-" * 70)
    
    try:
        # Ensure index exists
        create_search_index()
        
        # Index single page (automatically deletes old chunks first)
        chunks = index_single_page(page_id, space_key, delete_existing=True)
        print(f"   [OK] Indexed {chunks} chunks with embeddings")
        return True
    except Exception as e:
        print(f"   [ERROR] Indexing failed: {e}")
        return False


def step_6_generate_email(pages_results):
    """Step 6: Generate combined email digest using RAG for all pages"""
    print("\n")
    print("-" * 70)
    print("STEP 6: GENERATING EMAIL DIGEST")
    print("-" * 70)
    
    # For multi-page support, generate one email per page or combined
    # Currently generating per-page emails
    email_results = []
    
    for page_result in pages_results:
        page_id = page_result['page_id']
        page_title = page_result['page_title']
        version = page_result['version']
        has_changes = page_result['has_changes']
        change_summary = page_result.get('change_summary', 'No changes')
        previous_version = page_result.get('previous_version', None)
        
        try:
            result = generate_page_summary_email(
                page_id=page_id,
                page_title=page_title,
                version=version,
                has_changes=has_changes,
                change_summary=change_summary,
                previous_version=previous_version
            )
            
            if result:
                print(f"   [OK] Email generated for {page_title}")
                print(f"   HTML: {result['html_file']}")
                email_results.append(result)
        except Exception as e:
            print(f"   [ERROR] Email generation failed for {page_title}: {e}")
    
    return email_results


def process_single_page(page, force_reprocess=False, email_only=False):
    """
    Process a single page through the pipeline.
    
    Args:
        page: Page config dict with page_id, title, space_key
        force_reprocess: If True, run full pipeline even if no changes
        email_only: If True, skip extraction/indexing
    
    Returns:
        Dict with processing results
    """
    page_id = page['page_id']
    page_title = page['title']
    space_key = page['space_key']
    
    result = {
        'page_id': page_id,
        'page_title': page_title,
        'space_key': space_key,
        'status': 'unknown',
        'steps_completed': [],
        'errors': []
    }
    
    # Step 1: Detect changes
    change_result = step_1_detect_changes(page_id, page_title)
    result['steps_completed'].append('detect_changes')
    result['has_changes'] = change_result['has_changes']
    result['version'] = change_result['version_number']
    result['change_summary'] = change_result['change_summary']
    result['previous_version'] = change_result.get('previous_version', None)
    
    # Determine if we need to run full pipeline
    need_full_pipeline = (
        change_result['needs_reprocessing'] or 
        force_reprocess
    ) and not email_only
    
    if need_full_pipeline:
        print(f"\n>>> CHANGES DETECTED for {page_title} - Running full pipeline...")
        
        # Step 2: Extract content
        if step_2_extract_content(page_id, page_title, space_key):
            result['steps_completed'].append('extract_content')
        else:
            result['errors'].append('extract_content')
        
        # Step 3: Describe images
        if step_3_describe_images(page_id, page_title, space_key):
            result['steps_completed'].append('describe_images')
        else:
            result['errors'].append('describe_images')
        
        # Step 4: Upload to blob
        if step_4_upload_to_blob(page_id, page_title, space_key, change_result['version_number']):
            result['steps_completed'].append('upload_blob')
        else:
            result['errors'].append('upload_blob')
        
        # Step 5: Index in search (deletes old chunks first)
        if step_5_index_in_search(page_id, page_title, space_key):
            result['steps_completed'].append('index_search')
        else:
            result['errors'].append('index_search')
    
    else:
        print(f"\n>>> NO CHANGES for {page_title} - Skipping content processing...")
    
    # Final status
    if not result['errors']:
        result['status'] = 'success'
    else:
        result['status'] = 'partial_success'
    
    return result


def run_pipeline(force_reprocess=False, email_only=False):
    """
    Execute the complete pipeline for all configured pages.
    
    Args:
        force_reprocess: If True, run full pipeline even if no changes detected
        email_only: If True, only generate email (skip extraction/indexing)
    
    Returns:
        dict with pipeline results
    """
    # Load pages to monitor
    pages = get_pages_to_monitor()
    
    print_banner(pages)
    
    results = {
        'status': 'unknown',
        'started_at': datetime.utcnow().isoformat(),
        'pages_processed': [],
        'pages_changed': [],
        'steps_completed': [],
        'errors': [],
        'email_files': []
    }
    
    try:
        # Process each page
        for page in pages:
            page_result = process_single_page(page, force_reprocess, email_only)
            results['pages_processed'].append(page_result)
            
            if page_result['has_changes']:
                results['pages_changed'].append(page_result['page_id'])
        
        # Step 6: Generate emails (for all pages)
        email_results = step_6_generate_email(results['pages_processed'])
        
        if email_results:
            results['steps_completed'].append('generate_email')
            for er in email_results:
                results['email_files'].append(er['html_file'])
        else:
            results['errors'].append('generate_email')
        
        # Final status
        all_success = all(p['status'] == 'success' for p in results['pages_processed'])
        any_errors = any(p['errors'] for p in results['pages_processed']) or results['errors']
        
        if all_success and not any_errors:
            results['status'] = 'success'
        elif any_errors:
            results['status'] = 'partial_success'
        else:
            results['status'] = 'success'
        
    except Exception as e:
        results['status'] = 'failed'
        results['errors'].append(str(e))
    
    results['completed_at'] = datetime.utcnow().isoformat()
    
    # Print summary
    print("\n")
    print("=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)
    print(f"   Status: {results['status'].upper()}")
    print(f"   Pages processed: {len(results['pages_processed'])}")
    print(f"   Pages changed: {len(results['pages_changed'])}")
    
    if results['email_files']:
        print(f"   Emails generated: {len(results['email_files'])}")
        for ef in results['email_files']:
            print(f"     - {ef}")
    
    if results['errors']:
        print(f"   Errors: {results['errors']}")
    
    print("=" * 70)
    
    # Save results
    os.makedirs("data/runs", exist_ok=True)
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    results_file = f"data/runs/pipeline_run_{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n   Run log saved: {results_file}")
    
    return results


def main():
    """Main entry point with argument parsing"""
    parser = argparse.ArgumentParser(
        description='Confluence Weekly Digest Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                  Run complete workflow
  python main.py --force          Force full reprocessing
  python main.py --email-only     Only generate email digest
        """
    )
    
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Force full pipeline even if no changes detected'
    )
    
    parser.add_argument(
        '--email-only', '-e',
        action='store_true',
        help='Only generate email (skip extraction and indexing)'
    )
    
    args = parser.parse_args()
    
    result = run_pipeline(
        force_reprocess=args.force,
        email_only=args.email_only
    )
    
    # Exit code based on status
    if result['status'] == 'success':
        sys.exit(0)
    elif result['status'] == 'partial_success':
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
