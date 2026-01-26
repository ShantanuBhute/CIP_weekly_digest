"""
MASTER PIPELINE: Confluence to Blob Storage
Orchestrates: Extract → Describe → Upload
"""

import sys
from pathlib import Path
from confluence_content_extractor import extract_and_save_page
from image_description_generator import describe_images_in_document
from blob_storage_uploader import upload_page_to_blob

def run_pipeline(page_id, output_folder="data/pages"):
    """
    Complete pipeline: Confluence → Local → Blob Storage
    
    Args:
        page_id: Confluence page ID
        output_folder: Base folder for local storage
    
    Returns:
        dict with results from each step
    """
    
    print("=" * 80)
    print("🚀 CONFLUENCE TO BLOB STORAGE PIPELINE")
    print("=" * 80)
    print(f"\n📄 Target Page ID: {page_id}")
    
    results = {
        "page_id": page_id,
        "success": False,
        "steps": {}
    }
    
    # ========================================================================
    # STEP 1: Extract content from Confluence (COMMENTED - Already done)
    # ========================================================================
    # print("\n" + "=" * 80)
    # print("STEP 1/3: EXTRACTING CONFLUENCE CONTENT")
    # print("=" * 80)
    
    # SKIP - Using existing extracted data
    print("\n⏭️ STEP 1: SKIPPED (using existing data)")
    
    # Load existing document
    doc_folder = Path(output_folder) / "CIPPMOPF" / page_id
    doc_json_path = doc_folder / "document.json"
    
    if not doc_json_path.exists():
        print(f"❌ Document not found: {doc_json_path}")
        results['steps']['extract'] = {"success": False, "error": "Document not found"}
        return results
    
    import json
    with open(doc_json_path, 'r', encoding='utf-8') as f:
        document = json.load(f)
    
    space_key = document['metadata']['space_key']
    
    results['steps']['extract'] = {
        "success": True,
        "title": document['metadata']['title'],
        "space": space_key,
        "version": document['metadata']['version'],
        "blocks": document['metadata']['total_blocks'],
        "images": document['metadata']['total_images']
    }
    
    print(f"   ✅ Loaded: {document['metadata']['title']}")
    
    # ========================================================================
    # STEP 2: Generate image descriptions (COMMENTED - Already done)
    # ========================================================================
    # print("\n" + "=" * 80)
    # print("STEP 2/3: GENERATING IMAGE DESCRIPTIONS")
    # print("=" * 80)
    
    print("\n⏭️ STEP 2: SKIPPED (images already described)")
    
    results['steps']['describe'] = {
        "success": True,
        "images_processed": document['metadata'].get('total_images', 0),
        "tokens_used": document['metadata'].get('description_tokens_used', 0)
    }
    
    print(f"   ✅ Using existing descriptions")
    
    # ========================================================================
    # STEP 3: Upload to Azure Blob Storage
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 3/3: UPLOADING TO AZURE BLOB STORAGE")
    print("=" * 80)
    
    try:
        upload_result = upload_page_to_blob(str(doc_folder))
        
        if not upload_result['success']:
            results['steps']['upload'] = upload_result
            return results
        
        results['steps']['upload'] = {
            "success": True,
            "rag_filename": upload_result['rag_filename'],
            "rag_blob_url": upload_result['rag_blob_url'],
            "images_uploaded": upload_result['image_count']
        }
        
        print(f"\n✅ Step 3 Complete:")
        print(f"   📄 RAG document: {upload_result['rag_filename']}")
        print(f"   🖼️ {upload_result['image_count']} images uploaded")
        
    except Exception as e:
        print(f"\n❌ Step 3 Failed: {e}")
        results['steps']['upload'] = {"success": False, "error": str(e)}
        return results
    
    # ========================================================================
    # PIPELINE COMPLETE
    # ========================================================================
    results['success'] = True
    
    print("\n" + "=" * 80)
    print("🎉 PIPELINE COMPLETE - ALL STEPS SUCCESSFUL")
    print("=" * 80)
    
    print(f"\n📊 Summary:")
    print(f"   Page: {results['steps']['extract']['title']}")
    print(f"   Space: {results['steps']['extract']['space']}")
    print(f"   Version: v{results['steps']['extract']['version']}")
    print(f"   Content blocks: {results['steps']['extract']['blocks']}")
    print(f"   Images: {results['steps']['extract']['images']}")
    print(f"   Tokens used: {results['steps']['describe']['tokens_used']:,}")
    print(f"\n📦 Blob Storage:")
    print(f"   Container: confluence-rag")
    print(f"   Filename: {results['steps']['upload']['rag_filename']}")
    print(f"   URL: {results['steps']['upload']['rag_blob_url']}")
    
    return results


def main():
    """Main entry point"""
    
    # Default: ProPM Roles & Responsibilities
    # Change this to any Confluence page ID you want to process
    PAGE_ID = "164168599"
    
    # You can also pass page ID as command line argument
    if len(sys.argv) > 1:
        PAGE_ID = sys.argv[1]
    
    # Run the complete pipeline
    results = run_pipeline(PAGE_ID)
    
    # Exit with appropriate code
    if results['success']:
        print("\n✅ Pipeline succeeded!")
        sys.exit(0)
    else:
        print("\n❌ Pipeline failed. Check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
