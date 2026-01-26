"""
Complete Weekly Digest Pipeline
Runs the entire workflow: detect changes → summarize → save digest
"""

import os
import sys
import json
from datetime import datetime
from confluence_change_detector import detect_changes
from weekly_digest_summarizer import generate_weekly_digest, format_digest_html, format_digest_markdown


def run_weekly_digest(space_key="CIPPMOPF", days=7):
    """
    Complete end-to-end weekly digest generation
    
    Returns:
        dict with paths to generated files
    """
    print("\n" + "="*70)
    print("CONFLUENCE WEEKLY DIGEST PIPELINE")
    print("="*70 + "\n")
    
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    os.makedirs("data", exist_ok=True)
    
    # Step 1: Detect changes
    print("STEP 1: DETECTING CHANGES")
    print("-" * 70)
    changes = detect_changes(space_key, days)
    
    total_changes = changes['summary']['total_new'] + changes['summary']['total_updated']
    
    if total_changes == 0:
        print("\n✅ No changes detected. Digest generation skipped.\n")
        return {
            'status': 'no_changes',
            'message': 'No updates found in the specified period'
        }
    
    # Save changes
    changes_file = f"data/changes_{space_key}_{timestamp}.json"
    with open(changes_file, 'w') as f:
        json.dump(changes, f, indent=2)
    print(f"✅ Changes saved: {changes_file}\n")
    
    # Step 2: Generate digest
    print("STEP 2: GENERATING DIGEST")
    print("-" * 70)
    digest = generate_weekly_digest(changes_file)
    
    # Save outputs
    json_file = f"data/digest_{space_key}_{timestamp}.json"
    html_file = f"data/digest_{space_key}_{timestamp}.html"
    md_file = f"data/digest_{space_key}_{timestamp}.md"
    
    with open(json_file, 'w') as f:
        json.dump(digest, f, indent=2)
    
    with open(html_file, 'w') as f:
        f.write(format_digest_html(digest))
    
    with open(md_file, 'w') as f:
        f.write(format_digest_markdown(digest))
    
    print(f"\n✅ Digest files generated:")
    print(f"   JSON: {json_file}")
    print(f"   HTML: {html_file}")
    print(f"   Markdown: {md_file}")
    
    print("\n" + "="*70)
    print("PIPELINE COMPLETE")
    print("="*70 + "\n")
    
    return {
        'status': 'success',
        'changes_count': total_changes,
        'files': {
            'changes': changes_file,
            'digest_json': json_file,
            'digest_html': html_file,
            'digest_markdown': md_file
        },
        'digest': digest
    }


if __name__ == "__main__":
    # Parse arguments
    space_key = sys.argv[1] if len(sys.argv) > 1 else "CIPPMOPF"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    
    result = run_weekly_digest(space_key, days)
    
    if result['status'] == 'success':
        print(f"✅ Generated digest with {result['changes_count']} updates")
        print(f"\n📧 Send this email:")
        print(f"   HTML file: {result['files']['digest_html']}")
    else:
        print(f"ℹ️  {result['message']}")
