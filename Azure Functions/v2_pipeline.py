"""
V2 Pipeline - Optimized Confluence Content Processing
Integrates all V2 modules for efficient processing:

1. Change Detection (unchanged from v1 - already efficient)
2. Content Extraction (minimal changes - parsing is fast)
3. Image Processing (V2 - only download new/changed images)
4. Description Generation (V2 - cached by image hash)
5. Blob Upload (V2 - MD5 check before upload)
6. Search Indexing (unchanged)
7. Email Generation (unchanged)

Folder Structure:
confluence-content/
└── CIPPMOPF/
    └── {PageTitle}_{PageID}/
        ├── metadata.json
        ├── versions/v1.json, v2.json...
        ├── images/{hash}_{filename}
        └── descriptions/{hash}.json
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Add parent path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# V2 Modules
from v2_storage_manager import V2StorageManager, get_v2_storage_manager
from v2_image_manager import V2ImageManager, get_v2_image_manager
from v2_description_generator import V2DescriptionGenerator, get_v2_description_generator

# V1 Modules (still used for some operations)
from single_page_monitor import detect_changes_optimized
from confluence_content_extractor import get_page_details, ConfluenceContentParser

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Data folder (use /tmp in Azure Functions, local otherwise)
def get_data_folder() -> Path:
    if os.getenv("AZURE_FUNCTIONS_ENVIRONMENT"):
        return Path("/tmp/data")
    return Path("data")


class V2Pipeline:
    """
    Optimized pipeline with caching at every level:
    - Image download caching
    - Description caching
    - Upload deduplication
    """
    
    def __init__(self):
        self.storage = get_v2_storage_manager()
        self.image_manager = get_v2_image_manager(self.storage)
        self.description_generator = get_v2_description_generator(self.storage)
        
        self.stats = {
            'pages_processed': 0,
            'pages_changed': 0,
            'images_downloaded': 0,
            'images_cached': 0,
            'descriptions_generated': 0,
            'descriptions_cached': 0,
            'uploads_performed': 0,
            'uploads_skipped': 0,
            'estimated_cost_saved': 0.0
        }
    
    def process_page(self, page_id: str, force: bool = False) -> Dict:
        """
        Process a single page through the V2 pipeline.
        
        Args:
            page_id: Confluence page ID
            force: If True, reprocess even if no changes detected
        
        Returns:
            Processing result dict
        """
        result = {
            'page_id': page_id,
            'success': False,
            'has_changes': False,
            'steps_completed': [],
            'error': None
        }
        
        try:
            # ============================================================
            # STEP 1: Change Detection (unchanged from v1)
            # ============================================================
            logger.info(f"[{page_id}] Step 1: Checking for changes...")
            change_result = detect_changes_optimized(page_id)
            
            result['has_changes'] = change_result.get('has_changes', False) or force
            result['version'] = change_result.get('version_number', 1)
            result['previous_version'] = change_result.get('previous_version')
            result['title'] = change_result.get('title', f"Page {page_id}")
            result['change_summary'] = change_result.get('change_summary', '')
            result['steps_completed'].append('change_detection')
            
            if not result['has_changes']:
                logger.info(f"[{page_id}] No changes detected, skipping")
                result['success'] = True
                return result
            
            self.stats['pages_changed'] += 1
            
            # ============================================================
            # STEP 2: Content Extraction (parse HTML, get content blocks)
            # ============================================================
            logger.info(f"[{page_id}] Step 2: Extracting content...")
            
            page_data = get_page_details(page_id)
            if not page_data:
                raise Exception(f"Failed to fetch page {page_id}")
            
            title = page_data.get('title', 'Untitled')
            space_key = page_data.get('space', {}).get('key', 'CIPPMOPF')
            version = page_data.get('version', {}).get('number', 1)
            last_modified = page_data.get('version', {}).get('when', '')
            html_content = page_data.get('body', {}).get('storage', {}).get('value', '')
            
            # Parse content blocks
            parser = ConfluenceContentParser(page_id, os.getenv("CONFLUENCE_URL"), None)
            content_blocks = parser.parse(html_content)
            
            result['title'] = title
            result['space_key'] = space_key
            result['version'] = version
            result['steps_completed'].append('content_extraction')
            
            logger.info(f"[{page_id}] Extracted {len(content_blocks)} content blocks")
            
            # ============================================================
            # STEP 3: V2 Image Processing (only download new/changed)
            # ============================================================
            logger.info(f"[{page_id}] Step 3: Processing images (V2 optimized)...")
            
            data_folder = get_data_folder()
            local_folder = data_folder / "pages" / space_key / page_id
            local_folder.mkdir(parents=True, exist_ok=True)
            
            image_info = self.image_manager.process_page_images(
                page_id=page_id,
                space_key=space_key,
                page_title=title,
                content_blocks=content_blocks,
                local_folder=local_folder
            )
            
            # Update stats
            self.stats['images_downloaded'] += self.image_manager.download_stats['downloaded']
            self.stats['images_cached'] += self.image_manager.download_stats['skipped_cached']
            
            result['steps_completed'].append('image_processing')
            result['images_processed'] = len(image_info)
            
            # Update content blocks with blob URLs and local paths
            for block in content_blocks:
                if block.get('type') == 'image':
                    filename = block.get('filename', '')
                    if filename in image_info:
                        block['blob_url'] = image_info[filename].get('blob_url', '')
                        block['image_hash'] = image_info[filename].get('image_hash', '')
                        if image_info[filename].get('local_path'):
                            block['local_path'] = image_info[filename]['local_path']
            
            # ============================================================
            # STEP 4: V2 Description Generation (cached by hash)
            # ============================================================
            logger.info(f"[{page_id}] Step 4: Generating descriptions (V2 cached)...")
            
            descriptions = self.description_generator.process_page_images(
                page_id=page_id,
                space_key=space_key,
                page_title=title,
                image_info=image_info,
                content_blocks=content_blocks
            )
            
            # Update stats
            self.stats['descriptions_generated'] += self.description_generator.stats['generated']
            self.stats['descriptions_cached'] += self.description_generator.stats['from_cache']
            self.stats['estimated_cost_saved'] += self.description_generator.stats['cost_saved']
            
            # Update content blocks with descriptions
            for block in content_blocks:
                if block.get('type') == 'image':
                    filename = block.get('filename', '')
                    if filename in descriptions:
                        block['description'] = descriptions[filename].get('description', '')
                        block['description_type'] = descriptions[filename].get('image_type', 'general')
            
            result['steps_completed'].append('description_generation')
            result['descriptions_generated'] = len(descriptions)
            
            # ============================================================
            # STEP 5: Build & Upload Document
            # ============================================================
            logger.info(f"[{page_id}] Step 5: Uploading to blob storage (V2 deduplicated)...")
            
            # Build document structure
            document = {
                "metadata": {
                    "page_id": page_id,
                    "title": title,
                    "space_key": space_key,
                    "version": version,
                    "last_modified": last_modified,
                    "url": f"{os.getenv('CONFLUENCE_URL')}/wiki/spaces/{space_key}/pages/{page_id}",
                    "extracted_at": datetime.utcnow().isoformat() + "Z",
                    "total_blocks": len(content_blocks),
                    "images_described": True,
                    "v2_optimized": True
                },
                "content_blocks": content_blocks
            }
            
            # Upload version document
            uploaded, version_url = self.storage.upload_page_version(
                space_key, page_id, title, version, document
            )
            
            if uploaded:
                self.stats['uploads_performed'] += 1
            else:
                self.stats['uploads_skipped'] += 1
            
            # Update metadata
            self.storage.update_page_metadata(
                space_key, page_id, title, version,
                additional_metadata={
                    'images_count': len(image_info),
                    'descriptions_count': len(descriptions),
                    'change_summary': result['change_summary']
                }
            )
            
            result['steps_completed'].append('blob_upload')
            result['version_url'] = version_url
            
            # Save local document.json for compatibility with existing pipeline
            doc_json_path = local_folder / "document.json"
            with open(doc_json_path, 'w', encoding='utf-8') as f:
                json.dump(document, f, indent=2, ensure_ascii=False)
            
            result['document_path'] = str(doc_json_path)
            
            # ============================================================
            # SUCCESS
            # ============================================================
            result['success'] = True
            self.stats['pages_processed'] += 1
            
            logger.info(f"[{page_id}] ✅ Processing complete!")
            
        except Exception as e:
            logger.error(f"[{page_id}] ❌ Processing failed: {e}")
            result['error'] = str(e)
        
        return result
    
    def process_multiple_pages(self, page_ids: List[str], force: bool = False) -> Dict:
        """
        Process multiple pages and return combined results.
        """
        results = []
        
        for page_id in page_ids:
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing page: {page_id}")
            logger.info(f"{'='*60}")
            
            result = self.process_page(page_id, force)
            results.append(result)
        
        # Summary
        return {
            'pages_processed': len(results),
            'pages_with_changes': sum(1 for r in results if r.get('has_changes')),
            'pages_successful': sum(1 for r in results if r.get('success')),
            'stats': self.stats,
            'results': results
        }
    
    def print_summary(self):
        """Print optimization summary"""
        print("\n" + "=" * 70)
        print("V2 PIPELINE OPTIMIZATION SUMMARY")
        print("=" * 70)
        
        print(f"\n📄 Pages:")
        print(f"   • Processed: {self.stats['pages_processed']}")
        print(f"   • With changes: {self.stats['pages_changed']}")
        
        print(f"\n🖼️ Images:")
        print(f"   • Downloaded: {self.stats['images_downloaded']}")
        print(f"   • From cache: {self.stats['images_cached']} (skipped download)")
        
        print(f"\n📝 Descriptions:")
        print(f"   • Generated (GPT-4o): {self.stats['descriptions_generated']}")
        print(f"   • From cache: {self.stats['descriptions_cached']} (FREE)")
        print(f"   • Estimated cost saved: ${self.stats['estimated_cost_saved']:.2f}")
        
        print(f"\n📦 Uploads:")
        print(f"   • Performed: {self.stats['uploads_performed']}")
        print(f"   • Skipped (unchanged): {self.stats['uploads_skipped']}")
        
        print("\n" + "=" * 70)


def run_v2_pipeline(page_ids: List[str] = None, force: bool = False) -> Dict:
    """
    Main entry point for V2 pipeline.
    """
    # Get page IDs from env if not provided
    if page_ids is None:
        page_ids_str = os.getenv("PAGE_IDS", "")
        page_ids = [p.strip() for p in page_ids_str.split(",") if p.strip()]
    
    if not page_ids:
        logger.error("No page IDs configured")
        return {"error": "No page IDs configured"}
    
    # Run pipeline
    pipeline = V2Pipeline()
    result = pipeline.process_multiple_pages(page_ids, force)
    
    # Print summary
    pipeline.print_summary()
    
    return result


# CLI entry point
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="V2 Optimized Pipeline")
    parser.add_argument("--page", "-p", help="Single page ID to process")
    parser.add_argument("--force", "-f", action="store_true", help="Force reprocessing")
    args = parser.parse_args()
    
    print("=" * 70)
    print("V2 OPTIMIZED PIPELINE")
    print("=" * 70)
    print("Optimizations:")
    print("  ✓ Image caching - skip download if unchanged")
    print("  ✓ Description caching - skip GPT-4o if image unchanged")
    print("  ✓ Upload deduplication - skip upload if hash matches")
    print("=" * 70)
    
    if args.page:
        result = run_v2_pipeline([args.page], args.force)
    else:
        result = run_v2_pipeline(force=args.force)
    
    # Save result
    output_file = f"data/v2_run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs("data", exist_ok=True)
    with open(output_file, 'w') as f:
        # Exclude large content from results
        clean_results = []
        for r in result.get('results', []):
            clean_r = {k: v for k, v in r.items() if k != 'content_blocks'}
            clean_results.append(clean_r)
        result['results'] = clean_results
        json.dump(result, f, indent=2)
    
    print(f"\n✅ Results saved to: {output_file}")
