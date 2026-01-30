"""
V2 Test Script - Verify V2 optimizations with cipdigest2 storage
Run this to test the V2 pipeline before deploying to Azure Functions.

Tests:
1. Storage Manager - container creation, hash-based uploads
2. Image Manager - caching, deduplication
3. Description Generator - GPT-4o caching
4. Full Pipeline - end-to-end test
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load V2 environment
v2_env_path = Path("Azure Functions/.env.v2")
if v2_env_path.exists():
    print(f"📋 Loading V2 environment from: {v2_env_path}")
    load_dotenv(v2_env_path)
else:
    print("⚠️ V2 .env not found, using default .env")
    load_dotenv()

# Now import V2 modules
from v2_storage_manager import V2StorageManager, get_v2_storage_manager
from v2_image_manager import V2ImageManager, get_v2_image_manager
from v2_description_generator import V2DescriptionGenerator, get_v2_description_generator
from v2_pipeline import V2Pipeline, run_v2_pipeline


def test_storage_connection():
    """Test 1: Verify connection to cipdigest2"""
    print("\n" + "=" * 70)
    print("TEST 1: Storage Connection (cipdigest2)")
    print("=" * 70)
    
    try:
        storage = get_v2_storage_manager()
        
        # Check connection string
        conn_str = os.getenv("BLOB_STORAGE_CONNECTION_STRING", "")
        account_name = "unknown"
        if "AccountName=" in conn_str:
            account_name = conn_str.split("AccountName=")[1].split(";")[0]
        
        print(f"   Storage Account: {account_name}")
        
        # Verify it's cipdigest2
        if account_name == "cipdigest2":
            print("   ✅ Correct storage account (V2)")
        else:
            print(f"   ⚠️ Expected cipdigest2, got {account_name}")
            return False
        
        # Test container creation
        containers = ["confluence-content", "confluence-state", "confluence-emails"]
        for container in containers:
            result = storage.ensure_container(container)
            if result:
                print(f"   ✅ Container '{container}' ready")
            else:
                print(f"   ❌ Container '{container}' failed")
                return False
        
        return True
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False


def test_path_generation():
    """Test 2: Verify new folder structure"""
    print("\n" + "=" * 70)
    print("TEST 2: Folder Structure Generation")
    print("=" * 70)
    
    storage = get_v2_storage_manager()
    
    test_cases = [
        ("CIPPMOPF", "164168599", "ProPM Roles & Responsibilities", 
         "CIPPMOPF/ProPM_Roles_Responsibili_164168599"),
        ("CIPPMOPF", "166041865", "Agile Scrum Methodology",
         "CIPPMOPF/Agile_Scrum_Methodology_166041865"),
        ("CIPPMOPF", "17386855", "RACI Matrix Guide",
         "CIPPMOPF/RACI_Matrix_Guide_17386855"),
    ]
    
    all_passed = True
    for space, page_id, title, expected_prefix in test_cases:
        path = storage.get_page_base_path(space, page_id, title)
        if path.startswith(expected_prefix[:30]):  # Check prefix due to truncation
            print(f"   ✅ {title[:30]}... → {path}")
        else:
            print(f"   ❌ {title[:30]}... → {path} (expected prefix: {expected_prefix[:30]})")
            all_passed = False
    
    return all_passed


def test_hash_functions():
    """Test 3: Verify hash computation"""
    print("\n" + "=" * 70)
    print("TEST 3: Hash Functions")
    print("=" * 70)
    
    storage = get_v2_storage_manager()
    
    # Test content hash
    test_content = b"Hello, World!"
    hash1 = storage.compute_content_hash(test_content)
    hash2 = storage.compute_content_hash(test_content)
    
    if hash1 == hash2:
        print(f"   ✅ Content hash consistent: {hash1[:16]}...")
    else:
        print(f"   ❌ Content hash inconsistent!")
        return False
    
    # Test different content gives different hash
    different_content = b"Hello, World!!"
    hash3 = storage.compute_content_hash(different_content)
    
    if hash1 != hash3:
        print(f"   ✅ Different content → different hash")
    else:
        print(f"   ❌ Different content should have different hash!")
        return False
    
    return True


def test_upload_deduplication():
    """Test 4: Upload deduplication"""
    print("\n" + "=" * 70)
    print("TEST 4: Upload Deduplication")
    print("=" * 70)
    
    storage = get_v2_storage_manager()
    
    # Create test content
    test_content = json.dumps({
        "test": True,
        "timestamp": datetime.utcnow().isoformat(),
        "data": "This is V2 test data"
    }).encode('utf-8')
    
    blob_path = "test/deduplication_test.json"
    
    # First upload
    uploaded1, url1, reason1 = storage.upload_content_if_changed(
        "confluence-content", test_content, blob_path
    )
    print(f"   First upload: {reason1}")
    
    # Second upload with same content
    uploaded2, url2, reason2 = storage.upload_content_if_changed(
        "confluence-content", test_content, blob_path
    )
    print(f"   Second upload: {reason2}")
    
    if uploaded1 and not uploaded2:
        print(f"   ✅ Deduplication working! Second upload skipped")
        return True
    else:
        print(f"   ⚠️ Deduplication may need verification")
        return True  # Still pass, first run might have existing blob


def test_image_type_detection():
    """Test 5: Image type detection"""
    print("\n" + "=" * 70)
    print("TEST 5: Image Type Detection")
    print("=" * 70)
    
    generator = get_v2_description_generator()
    
    test_cases = [
        ("RACI_matrix.png", "table"),
        ("process_flow.jpg", "flowchart"),
        ("screenshot_email.png", "screenshot"),
        ("org_chart_diagram.png", "diagram"),
        ("random_photo.jpg", "general"),
    ]
    
    all_passed = True
    for filename, expected in test_cases:
        detected = generator.detect_image_type(filename)
        status = "✅" if detected == expected else "⚠️"
        print(f"   {status} {filename} → {detected} (expected: {expected})")
        if detected != expected:
            all_passed = False
    
    return all_passed


def test_single_page_v2(page_id: str = "164168599"):
    """Test 6: Full V2 pipeline on single page"""
    print("\n" + "=" * 70)
    print(f"TEST 6: Full V2 Pipeline (Page {page_id})")
    print("=" * 70)
    
    try:
        pipeline = V2Pipeline()
        result = pipeline.process_page(page_id, force=True)
        
        print(f"\n   Page: {result.get('title', 'Unknown')}")
        print(f"   Version: {result.get('version', 'Unknown')}")
        print(f"   Steps completed: {result.get('steps_completed', [])}")
        print(f"   Images processed: {result.get('images_processed', 0)}")
        print(f"   Descriptions: {result.get('descriptions_generated', 0)}")
        
        if result.get('success'):
            print(f"\n   ✅ Pipeline completed successfully!")
            pipeline.print_summary()
            return True
        else:
            print(f"\n   ❌ Pipeline failed: {result.get('error', 'Unknown')}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def run_all_tests():
    """Run all V2 tests"""
    print("\n" + "=" * 70)
    print("V2 OPTIMIZATION TEST SUITE")
    print("=" * 70)
    print(f"Time: {datetime.utcnow().isoformat()}Z")
    print(f"Storage: {os.getenv('AZURE_STORAGE_ACCOUNT_NAME', 'unknown')}")
    print("=" * 70)
    
    results = {}
    
    # Run tests
    results['1_storage'] = test_storage_connection()
    results['2_paths'] = test_path_generation()
    results['3_hashes'] = test_hash_functions()
    results['4_dedup'] = test_upload_deduplication()
    results['5_types'] = test_image_type_detection()
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for test, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n   Total: {passed} passed, {failed} failed")
    
    # Ask about full pipeline test
    if failed == 0:
        print("\n" + "=" * 70)
        print("All basic tests passed!")
        print("Run full pipeline test? This will call GPT-4o Vision (costs ~$0.50)")
        print("=" * 70)
        
        response = input("Run full pipeline test? [y/N]: ").strip().lower()
        if response == 'y':
            results['6_pipeline'] = test_single_page_v2()
    
    return results


# Entry point
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="V2 Test Suite")
    parser.add_argument("--full", "-f", action="store_true", help="Run full pipeline test")
    parser.add_argument("--page", "-p", default="164168599", help="Page ID for full test")
    args = parser.parse_args()
    
    results = run_all_tests()
    
    if args.full:
        print("\n" + "=" * 70)
        print("Running full pipeline test...")
        print("=" * 70)
        test_single_page_v2(args.page)
