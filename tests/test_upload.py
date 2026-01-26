"""
Test Upload Only - Skip extraction and description (already done)
"""

from pathlib import Path
from blob_storage_uploader import upload_page_to_blob

def main():
    """Upload existing document to blob storage"""
    
    print("=" * 80)
    print("🚀 TESTING BLOB STORAGE UPLOAD")
    print("=" * 80)
    
    # Path to existing document
    doc_folder = "data/pages/CIPPMOPF/164168599"
    
    if not Path(doc_folder).exists():
        print(f"❌ Document folder not found: {doc_folder}")
        print("Run confluence_content_extractor.py first!")
        return
    
    # Upload to blob storage
    result = upload_page_to_blob(doc_folder)
    
    if result['success']:
        print("\n✅ Upload succeeded!")
        print(f"\n📦 RAG Document:")
        print(f"   Filename: {result['rag_filename']}")
        print(f"   URL: {result['rag_blob_url']}")
    else:
        print("\n❌ Upload failed!")
        print(f"Error: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
