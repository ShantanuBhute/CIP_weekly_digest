"""
Weekly Digest Summarizer
Generates AI-powered summaries of Confluence changes using GPT-4o
"""

import os
import json
import httpx
from datetime import datetime
from dotenv import load_dotenv
from openai import AzureOpenAI
from confluence_content_extractor import ConfluenceContentParser

load_dotenv()

# Azure OpenAI configuration
openai_client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
    http_client=httpx.Client(verify=False)
)

MODEL = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")


def extract_page_content(page_id):
    """Extract full content from a Confluence page"""
    parser = ConfluenceContentParser()
    
    try:
        print(f"   📄 Extracting content from page {page_id}...")
        document = parser.get_page_content(page_id)
        
        # Build text representation
        content_text = ""
        for block in document['content_blocks']:
            if block['type'] == 'heading':
                content_text += f"\n## {block['content']}\n"
            elif block['type'] == 'text':
                content_text += f"{block['content']}\n"
            elif block['type'] == 'list':
                for item in block.get('items', []):
                    content_text += f"• {item}\n"
            elif block['type'] == 'table':
                content_text += "\n[TABLE]\n"
                for row in block.get('rows', []):
                    content_text += " | ".join(row) + "\n"
            elif block['type'] == 'image':
                desc = block.get('description', block.get('filename', ''))
                content_text += f"\n[IMAGE: {desc}]\n"
        
        return {
            'page_id': page_id,
            'title': document['metadata']['title'],
            'content': content_text[:8000],  # Limit for LLM context
            'url': document['metadata']['url']
        }
    
    except Exception as e:
        print(f"   ❌ Error extracting page: {e}")
        return None


def summarize_page_changes(page_info, content):
    """
    Generate AI summary of what changed in a page
    """
    prompt = f"""You are analyzing updates to a Confluence page for a weekly digest.

Page Title: {page_info['title']}
Version: {page_info.get('previous_version', 'N/A')} → {page_info['version']}
Last Modified: {page_info['last_modified']}

Page Content:
{content}

Generate a concise summary (2-3 sentences) highlighting:
1. What this page is about
2. Key information or updates (if this is an update, focus on what likely changed)

Be specific and actionable. Focus on business value.

Summary:"""

    try:
        response = openai_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes Confluence page updates for executive digests."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        print(f"   ❌ Summarization error: {e}")
        return "Summary generation failed."


def generate_weekly_digest(changes_file):
    """
    Generate a complete weekly digest from detected changes
    """
    print("\n" + "="*70)
    print("GENERATING WEEKLY DIGEST")
    print("="*70 + "\n")
    
    # Load changes
    with open(changes_file, 'r') as f:
        changes = json.load(f)
    
    digest = {
        'title': f"Weekly Digest - {changes['summary']['space_key']}",
        'generated_at': datetime.utcnow().isoformat(),
        'period': f"Last 7 days",
        'summary': changes['summary'],
        'sections': []
    }
    
    # Process new pages
    if changes['new_pages']:
        print(f"📝 Summarizing {len(changes['new_pages'])} new pages...\n")
        new_section = {
            'title': '🆕 New Pages',
            'items': []
        }
        
        for page in changes['new_pages']:
            print(f"   Processing: {page['title']}")
            
            # Extract content
            page_content = extract_page_content(page['id'])
            if not page_content:
                continue
            
            # Generate summary
            summary = summarize_page_changes(page, page_content['content'])
            
            new_section['items'].append({
                'title': page['title'],
                'url': page['url'],
                'summary': summary,
                'version': page['version'],
                'last_modified': page['last_modified']
            })
            
            print(f"   ✅ Summary: {summary[:80]}...\n")
        
        digest['sections'].append(new_section)
    
    # Process updated pages
    if changes['updated_pages']:
        print(f"\n✏️  Summarizing {len(changes['updated_pages'])} updated pages...\n")
        updated_section = {
            'title': '✏️ Updated Pages',
            'items': []
        }
        
        for page in changes['updated_pages']:
            print(f"   Processing: {page['title']}")
            
            # Extract content
            page_content = extract_page_content(page['id'])
            if not page_content:
                continue
            
            # Generate summary
            summary = summarize_page_changes(page, page_content['content'])
            
            updated_section['items'].append({
                'title': page['title'],
                'url': page['url'],
                'summary': summary,
                'version': f"{page['previous_version']} → {page['version']}",
                'last_modified': page['last_modified']
            })
            
            print(f"   ✅ Summary: {summary[:80]}...\n")
        
        digest['sections'].append(updated_section)
    
    print("="*70)
    print(f"✅ DIGEST COMPLETE")
    print(f"   Total items: {sum(len(s['items']) for s in digest['sections'])}")
    print("="*70 + "\n")
    
    return digest


def format_digest_html(digest):
    """Format digest as HTML email"""
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #0066cc; border-bottom: 3px solid #0066cc; padding-bottom: 10px; }}
        h2 {{ color: #333; margin-top: 30px; }}
        .item {{ background: #f9f9f9; border-left: 4px solid #0066cc; padding: 15px; margin: 15px 0; }}
        .item-title {{ font-size: 18px; font-weight: bold; margin-bottom: 5px; }}
        .item-title a {{ color: #0066cc; text-decoration: none; }}
        .item-title a:hover {{ text-decoration: underline; }}
        .item-meta {{ font-size: 12px; color: #666; margin-bottom: 10px; }}
        .item-summary {{ font-size: 14px; line-height: 1.5; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <h1>{digest['title']}</h1>
    <p><strong>Period:</strong> {digest['period']}<br>
    <strong>Generated:</strong> {digest['generated_at'][:10]}</p>
    
    <p><strong>Summary:</strong> {digest['summary']['total_new']} new pages, {digest['summary']['total_updated']} updated pages</p>
"""
    
    for section in digest['sections']:
        html += f"\n    <h2>{section['title']}</h2>\n"
        
        for item in section['items']:
            html += f"""
    <div class="item">
        <div class="item-title"><a href="{item['url']}">{item['title']}</a></div>
        <div class="item-meta">Version: {item['version']} | Last Modified: {item['last_modified'][:10]}</div>
        <div class="item-summary">{item['summary']}</div>
    </div>
"""
    
    html += """
    <div class="footer">
        This digest was automatically generated from Confluence updates.
    </div>
</body>
</html>
"""
    
    return html


def format_digest_markdown(digest):
    """Format digest as Markdown"""
    md = f"""# {digest['title']}

**Period:** {digest['period']}  
**Generated:** {digest['generated_at'][:10]}

**Summary:** {digest['summary']['total_new']} new pages, {digest['summary']['total_updated']} updated pages

---

"""
    
    for section in digest['sections']:
        md += f"\n## {section['title']}\n\n"
        
        for item in section['items']:
            md += f"""### [{item['title']}]({item['url']})

**Version:** {item['version']} | **Last Modified:** {item['last_modified'][:10]}

{item['summary']}

---

"""
    
    md += "\n*This digest was automatically generated from Confluence updates.*\n"
    
    return md


def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python weekly_digest_summarizer.py <changes_json_file>")
        sys.exit(1)
    
    changes_file = sys.argv[1]
    
    # Generate digest
    digest = generate_weekly_digest(changes_file)
    
    # Save outputs
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    
    # JSON
    json_file = f"data/digest_{timestamp}.json"
    with open(json_file, 'w') as f:
        json.dump(digest, f, indent=2)
    print(f"✅ JSON saved: {json_file}")
    
    # HTML
    html_file = f"data/digest_{timestamp}.html"
    with open(html_file, 'w') as f:
        f.write(format_digest_html(digest))
    print(f"✅ HTML saved: {html_file}")
    
    # Markdown
    md_file = f"data/digest_{timestamp}.md"
    with open(md_file, 'w') as f:
        f.write(format_digest_markdown(digest))
    print(f"✅ Markdown saved: {md_file}")


if __name__ == "__main__":
    main()
