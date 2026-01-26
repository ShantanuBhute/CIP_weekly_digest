"""
Single Page Pipeline - Complete Workflow
Monitors ProPM Roles & Responsibilities page and generates email digest

Workflow:
1. Check for changes (text comparison)
2. If changed → Re-run full pipeline (extract, describe, upload, index)
3. If unchanged → Use existing indexed data
4. Generate email summary from indexed content
"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv

# Import pipeline components
from single_page_monitor import detect_changes_optimized, PAGE_ID, PAGE_TITLE, SPACE_KEY
from confluence_content_extractor import ConfluenceContentParser
from image_description_generator import describe_images_in_document
from blob_storage_uploader import upload_page_to_blob
from azure_search_indexer import index_documents_from_blob
from email_digest_generator import generate_page_summary_email

load_dotenv()


def run_full_pipeline(page_id, version_number):
    """
    Run complete processing pipeline for changed content
    """
    print("\n" + "="*70)
    print("FULL PIPELINE EXECUTION")
    print("="*70 + "\n")
    
    output_dir = f"data/pages/{SPACE_KEY}/{page_id}"
    os.makedirs(output_dir, exist_ok=True)
    
    # Step 1: Extract content with images
    print("STEP 1: EXTRACTING CONTENT")
    print("-" * 70)
    parser = ConfluenceContentParser()
    document = parser.extract_and_save_page(page_id, SPACE_KEY)
    print(f"✅ Extracted {len(document['content_blocks'])} content blocks\n")
    
    # Step 2: Describe images with GPT-4o Vision
    print("STEP 2: DESCRIBING IMAGES")
    print("-" * 70)
    document_path = f"{output_dir}/document.json"
    with open(document_path, 'r') as f:
        doc = json.load(f)
    
    updated_doc = describe_images_in_document(document_path)
    print(f"✅ Described images\n")
    
    # Step 3: Upload to blob storage
    print("STEP 3: UPLOADING TO BLOB STORAGE")
    print("-" * 70)
    blob_url = upload_page_to_blob(page_id, SPACE_KEY, version_number)
    print(f"✅ Uploaded to: {blob_url}\n")
    
    # Step 4: Index in Azure AI Search
    print("STEP 4: INDEXING IN AZURE AI SEARCH")
    print("-" * 70)
    chunks_indexed = index_documents_from_blob()
    print(f"✅ Indexed {chunks_indexed} chunks\n")
    
    print("="*70)
    print("PIPELINE COMPLETE")
    print("="*70 + "\n")
    
    return {
        'status': 'success',
        'chunks_indexed': chunks_indexed,
        'blob_url': blob_url,
        'document_path': document_path
    }


def run_single_page_workflow():
    """
    Complete workflow for single page monitoring
    """
    print("\n" + "="*80)
    print("PROPM ROLES & RESPONSIBILITIES - MONITORING WORKFLOW")
    print("="*80 + "\n")
    
    print(f"📄 Target Page: {PAGE_TITLE}")
    print(f"🔗 URL: https://eaton-corp.atlassian.net/wiki/spaces/{SPACE_KEY}/pages/{PAGE_ID}")
    print(f"🆔 Page ID: {PAGE_ID}\n")
    
    # STEP 1: Detect changes
    print("PHASE 1: CHANGE DETECTION")
    print("="*80)
    
    change_result = detect_changes_optimized(PAGE_ID)
    
    # STEP 2: Process if needed
    if change_result['needs_reprocessing']:
        print("\n📢 CHANGES DETECTED - Running full pipeline...\n")
        
        print("PHASE 2: CONTENT PROCESSING")
        print("="*80)
        
        pipeline_result = run_full_pipeline(PAGE_ID, change_result['version_number'])
        
        status_message = f"Page updated to v{change_result['version_number']}"
        reprocessed = True
    
    else:
        print("\n✅ NO CHANGES - Using existing indexed content\n")
        
        status_message = f"Page unchanged (v{change_result['version_number']})"
        reprocessed = False
    
    # STEP 3: Generate email summary
    print("PHASE 3: EMAIL DIGEST GENERATION")
    print("="*80)
    
    email_result = generate_page_summary_email(
        page_id=PAGE_ID,
        page_title=PAGE_TITLE,
        version=change_result['version_number'],
        has_changes=change_result['has_changes'],
        change_summary=change_result['change_summary']
    )
    
    # Final summary
    print("\n" + "="*80)
    print("WORKFLOW COMPLETE")
    print("="*80)
    print(f"📊 Status: {status_message}")
    print(f"📧 Email: {email_result['html_file']}")
    print(f"🔄 Reprocessed: {reprocessed}")
    print("="*80 + "\n")
    
    return {
        'status': 'success',
        'version': change_result['version_number'],
        'has_changes': change_result['has_changes'],
        'reprocessed': reprocessed,
        'email_html': email_result['html_file'],
        'email_json': email_result['json_file']
    }


if __name__ == "__main__":
    result = run_single_page_workflow()
    
    # Save workflow result
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    result_file = f"data/workflow_result_{timestamp}.json"
    
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"✅ Workflow result saved: {result_file}")
