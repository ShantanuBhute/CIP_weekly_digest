"""
Email Digest Generator
Creates beautiful HTML email summaries using indexed content and GPT-4o
"""

import os
import json
import httpx
from datetime import datetime
from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential

load_dotenv()

# Azure OpenAI configuration
openai_client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
    http_client=httpx.Client(verify=False)
)

# Azure AI Search configuration
SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")
SEARCH_INDEX_NAME = "confluence-rag-index"

# Embedding configuration
embedding_client = AzureOpenAI(
    azure_endpoint=os.getenv("FOUNDRY_EMBEDDING_ENDPOINT"),
    api_key=os.getenv("FOUNDRY_EMBEDDING_API_KEY"),
    api_version="2024-02-01",
    http_client=httpx.Client(verify=False)
)

MODEL = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
EMBEDDING_MODEL = os.getenv("FOUNDRY_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")


def retrieve_page_content(page_id):
    """
    Retrieve all indexed chunks for a page from Azure AI Search
    """
    print(f"🔍 Retrieving indexed content for page {page_id}...")
    
    search_client = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=SEARCH_INDEX_NAME,
        credential=AzureKeyCredential(SEARCH_API_KEY),
        connection_verify=False
    )
    
    # Get all chunks for this page
    results = search_client.search(
        search_text="*",
        filter=f"page_id eq '{page_id}'",
        select=["chunk_id", "chunk_index", "content_type", "content_text", "has_image", "image_description", "image_url"]
    )
    
    # Sort by chunk_index after retrieval
    chunks = sorted(list(results), key=lambda x: x.get('chunk_index', 0))
    print(f"✅ Retrieved {len(chunks)} chunks\n")
    
    return chunks


def generate_summary_with_rag(page_title, chunks, has_changes, change_summary):
    """
    Generate email summary using GPT-4o with RAG context.
    Addresses both technical and managerial audiences.
    """
    print(f"🤖 Generating AI summary...\n")
    
    # Build context from chunks - prioritize image descriptions
    context = f"Page Title: {page_title}\n\n"
    
    # First, collect ALL image descriptions across all chunks
    # Image descriptions are stored as "[TYPE] filename: description" separated by "\n\n"
    all_image_descriptions = []
    for chunk in chunks:
        if chunk.get('has_image') and chunk.get('image_description'):
            img_desc_field = chunk['image_description']
            # Split by the [TYPE] pattern to get individual image descriptions
            import re
            # Split on patterns like [TABLE], [GENERAL], [FLOWCHART], etc.
            parts = re.split(r'\n\n(?=\[(?:TABLE|GENERAL|FLOWCHART|DIAGRAM|SCREENSHOT)\])', img_desc_field)
            for part in parts:
                if part.strip():
                    all_image_descriptions.append(part.strip())
    
    # Debug: show how many images we found
    print(f"   📷 Found {len(all_image_descriptions)} image description(s)")
    
    # Add image descriptions prominently at the start - GPT MUST use ALL of these
    if all_image_descriptions:
        context += "=== VISUAL CONTENT (Diagrams, Tables, Screenshots) - SUMMARIZE ALL ===\n"
        for i, img_desc in enumerate(all_image_descriptions, 1):
            # Increased limit to 2500 chars per image for comprehensive content
            context += f"\n📷 IMAGE {i}:\n{img_desc[:2500]}\n"
        context += "\n=== END VISUAL CONTENT - ALL IMAGES ABOVE MUST BE IN SUMMARY ===\n\n"
    
    # Then add text content
    context += "=== TEXT CONTENT ===\n"
    for chunk in chunks:
        content_text = chunk.get('content_text', '')
        if content_text:
            # Remove image descriptions from content_text to avoid duplication
            # Just keep the non-image parts
            lines = content_text.split('\n')
            text_lines = []
            skip_until_next_section = False
            for line in lines:
                if '📷 IMAGE' in line:
                    skip_until_next_section = True
                    continue
                if skip_until_next_section and line.strip().startswith('#'):
                    skip_until_next_section = False
                if not skip_until_next_section:
                    text_lines.append(line)
            clean_text = '\n'.join(text_lines)
            if clean_text.strip():
                context += f"{clean_text[:1500]}\n\n"
    
    # Build prompt for dual audience (technical + managerial)
    if has_changes:
        prompt = f"""Create a COMPREHENSIVE executive email digest for a Confluence page.

Page: {page_title}

Page Content:
{context[:15000]}

INSTRUCTIONS:
Write a detailed professional email covering ALL content. Include these sections:

Overview:
2-3 sentences summarizing what this page is about.

Key Content (MUST include ALL items below):
• Summarize EVERY image/diagram mentioned in the content - do not skip any
• For each IMAGE section, extract and explain what it represents
• Include all processes, workflows, matrices, and screenshots described

For Technical Teams:
• All processes, workflows, and responsibilities
• All RACI assignments - who is Responsible/Accountable/Consulted/Informed
• All process steps from any flowcharts or diagrams
• All system/tool information from screenshots
• Action items or procedures

For Managers & Stakeholders:
• Business impact and strategic relevance
• Resource implications and ownership
• Key governance or decision points

CRITICAL RULES:
- You MUST include insights from EVERY 📷 IMAGE section - do not skip any
- You MUST include ALL text content - even if it seems off-topic or tangential
- NOTHING can be skipped or left out - comprehensive coverage is required
- Use ONLY single-level bullets (•)
- NO markdown formatting
- Focus on INTERPRETATION (what it means) not visual description
- Do NOT fabricate information

Sign off as:
Best regards,
CIP Weekly Digest"""
    
    else:
        prompt = f"""Create a COMPREHENSIVE executive email digest for a Confluence page.

Page: {page_title}

Page Content:
{context[:15000]}

INSTRUCTIONS:
Write a detailed professional email covering ALL content. Include these sections:

Overview:
2-3 sentences summarizing what this page is about.

Key Content (MUST include ALL items below):
• Summarize EVERY image/diagram mentioned in the content - do not skip any
• For each IMAGE section, extract and explain what it represents
• Include all processes, workflows, matrices, and screenshots described

For Technical Teams:
• All processes, workflows, and responsibilities
• All RACI assignments - who is Responsible/Accountable/Consulted/Informed
• All process steps from any flowcharts or diagrams  
• All system/tool information from screenshots
• Action items or procedures

For Managers & Stakeholders:
• Business relevance and strategic importance
• Resource implications and ownership
• Key governance or decision points

CRITICAL RULES:
- You MUST include insights from EVERY 📷 IMAGE section - do not skip any
- You MUST include ALL text content - even if it seems off-topic or tangential
- NOTHING can be skipped or left out - comprehensive coverage is required
- Use ONLY single-level bullets (•)
- NO markdown formatting
- Focus on INTERPRETATION (what it means) not visual description
- Do NOT fabricate information
- If page has limited content, say so honestly

Sign off as:
Best regards,
CIP Weekly Digest"""
    
    try:
        response = openai_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": """You write COMPREHENSIVE executive summaries from Confluence documentation.

CRITICAL - INCLUDE EVERYTHING (NO EXCEPTIONS):
1. You MUST include insights from EVERY 📷 IMAGE section provided
2. You MUST include ALL text content - even if it seems unrelated to the main topic
3. Each image/diagram/screenshot MUST be summarized in your response
4. Do not skip ANY content - if it's in the input, it MUST be in the summary
5. Off-topic or tangential content still gets included - let the reader decide relevance
6. NEVER FABRICATE - only include information explicitly in the content

HANDLING IMAGES/DIAGRAMS:
- 📷 IMAGE sections contain descriptions of diagrams, flowcharts, RACI matrices, screenshots
- You MUST summarize EACH image - what it represents and key information
- For RACI matrices: list all role assignments
- For flowcharts: list all process steps
- For screenshots: describe what system/tool it shows and key data visible
- Focus on MEANING and INTERPRETATION, not visual appearance
- NEVER skip an image because it seems less relevant

HANDLING TEXT CONTENT:
- Include ALL text sections even if they seem off-topic or tangential
- If there are notes, comments, or side information - include them
- Do not filter based on perceived relevance - include everything
- The reader will decide what's relevant to them

FORMATTING:
- Use ONLY single-level bullets (•)
- NO markdown (**, ##, -, etc.)
- Sign off as "CIP Weekly Digest"""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000  # Increased for comprehensive coverage
        )
        
        summary = response.choices[0].message.content.strip()
        
        # Clean up any markdown or nested formatting
        summary = summary.replace('**', '')
        summary = summary.replace('__', '')
        summary = summary.replace('###', '')
        summary = summary.replace('##', '')
        summary = summary.replace('# ', '')
        summary = summary.replace('[Your Name]', 'CIP Weekly Digest')
        summary = summary.replace('[Your Position]', '')
        summary = summary.replace('  •', '•')  # Remove indented bullets
        summary = summary.replace('   •', '•')
        summary = summary.replace('    •', '•')
        summary = summary.replace('  -', '•')
        summary = summary.replace('   -', '•')
        summary = summary.replace('    -', '•')
        summary = summary.replace(' - ', ' • ')
        
        # Extract token usage
        usage = response.usage
        print(f"✅ Summary generated")
        print(f"   Tokens: {usage.total_tokens} (prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens})\n")
        
        return summary
    
    except Exception as e:
        print(f"❌ Summary generation failed: {e}\n")
        return f"Error generating summary. Please review the page directly."


def format_summary_html(summary):
    """
    Convert summary text to properly formatted HTML.
    Handles line breaks and ensures proper paragraph structure.
    FLAT bullets only - no nesting.
    """
    # Clean up markdown artifacts
    summary = summary.replace('**', '')
    summary = summary.replace('__', '')
    summary = summary.replace('[Your Name]', 'CIP Weekly Digest')
    summary = summary.replace('[Your Position]', '')
    
    lines = summary.split('\n')
    formatted_parts = []
    in_bullet_list = False
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_bullet_list:
                formatted_parts.append('</ul>')
                in_bullet_list = False
            continue
        
        # Check if it's a section header (ends with : and is short)
        if line.endswith(':') and len(line) < 50 and not line.startswith('•'):
            if in_bullet_list:
                formatted_parts.append('</ul>')
                in_bullet_list = False
            formatted_parts.append(f'<p style="margin: 15px 0 5px 0;"><strong style="color: #1a73e8;">{line}</strong></p>')
        
        # Check if it's a bullet point
        elif line.startswith('•') or line.startswith('-') or line.startswith('*'):
            # Clean the bullet
            bullet_text = line.lstrip('•-* ').strip()
            if not in_bullet_list:
                formatted_parts.append('<ul style="margin: 5px 0 10px 15px; padding: 0; list-style-type: disc;">')
                in_bullet_list = True
            formatted_parts.append(f'<li style="margin: 4px 0;">{bullet_text}</li>')
        
        # Regular paragraph
        else:
            if in_bullet_list:
                formatted_parts.append('</ul>')
                in_bullet_list = False
            formatted_parts.append(f'<p style="margin: 8px 0; line-height: 1.5;">{line}</p>')
    
    # Close any open list
    if in_bullet_list:
        formatted_parts.append('</ul>')
    
    return '\n'.join(formatted_parts)


def format_email_html(page_title, page_url, version, summary, chunks, has_changes, change_summary):
    """
    Format beautiful HTML email
    """
    # Simple status - no prominent banners
    status_banner = ""
    
    # Build content preview - show sections now instead of chunks
    content_preview = "<h3 style='margin-bottom: 10px;'>📄 Page Sections</h3><ul style='margin: 0; padding-left: 20px;'>"
    for chunk in chunks[:8]:  # Show first 8 sections
        content_text = chunk.get('content_text', '')
        # Get first line as section title
        first_line = content_text.split('\n')[0].strip('#').strip()[:60]
        if first_line:
            content_preview += f"<li style='margin: 4px 0;'>{first_line}</li>"
    content_preview += "</ul>"
    
    if len(chunks) > 8:
        content_preview += f"<p style='margin: 5px 0; font-style: italic;'>...and {len(chunks) - 8} more sections</p>"
    
    # Format summary using the new formatter
    formatted_summary = format_summary_html(summary)
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            line-height: 1.5;
            color: #333;
            max-width: 700px;
            margin: 0 auto;
            padding: 15px;
            background: #f5f5f5;
        }}
        .email-container {{
            background: white;
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #1a73e8;
            margin: 0 0 15px 0;
            border-bottom: 3px solid #1a73e8;
            padding-bottom: 12px;
            font-size: 22px;
        }}
        h2 {{
            color: #5f6368;
            margin: 20px 0 10px 0;
            font-size: 18px;
        }}
        h3 {{
            color: #5f6368;
            margin: 15px 0 8px 0;
            font-size: 16px;
        }}
        h4 {{
            color: #1a73e8;
            margin: 12px 0 6px 0;
            font-size: 14px;
        }}
        .meta {{
            background: #f8f9fa;
            padding: 12px;
            border-radius: 5px;
            margin: 15px 0;
            font-size: 13px;
            line-height: 1.6;
        }}
        .meta strong {{
            color: #1a73e8;
        }}
        .summary {{
            background: #e8f0fe;
            border-left: 4px solid #1a73e8;
            padding: 15px;
            margin: 15px 0;
            font-size: 14px;
            line-height: 1.5;
        }}
        .summary p {{
            margin: 6px 0;
        }}
        .summary ul {{
            margin: 5px 0;
            padding-left: 20px;
        }}
        .summary li {{
            margin: 3px 0;
        }}
        .btn {{
            display: inline-block;
            background: #1a73e8;
            color: white !important;
            padding: 10px 25px;
            text-decoration: none;
            border-radius: 5px;
            font-weight: 500;
            margin: 15px 0;
            font-size: 14px;
        }}
        .btn:hover {{
            background: #1557b0;
        }}
        .content-preview {{
            background: #fafafa;
            padding: 15px;
            border-radius: 5px;
            margin: 15px 0;
            font-size: 13px;
        }}
        .content-preview ul {{
            margin: 5px 0;
            padding-left: 20px;
        }}
        .content-preview li {{
            margin: 4px 0;
        }}
        .footer {{
            margin-top: 25px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
            font-size: 12px;
            color: #666;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <h1>📋 {page_title}</h1>
        
        <div class="meta">
            <strong>📅 Generated:</strong> {datetime.utcnow().strftime('%B %d, %Y at %H:%M UTC')}<br>
            <strong>📝 Version:</strong> v{version}<br>
            <strong>🔗 Link:</strong> <a href="{page_url}">{page_url}</a>
        </div>
        
        {status_banner}
        
        <h2>📝 Executive Summary</h2>
        <div class="summary">
            {formatted_summary}
        </div>
        
        <a href="{page_url}" class="btn">📖 View Full Page in Confluence</a>
        
        <div class="content-preview">
            {content_preview}
        </div>
        
        <div class="footer">
            This digest was automatically generated from Confluence content.<br>
            Powered by Azure AI and GPT-4o
        </div>
    </div>
</body>
</html>"""
    
    return html


def generate_page_summary_email(page_id, page_title, version, has_changes, change_summary):
    """
    Main function to generate complete email digest
    """
    print("\n" + "="*70)
    print("EMAIL DIGEST GENERATION")
    print("="*70 + "\n")
    
    # Step 1: Retrieve indexed content
    chunks = retrieve_page_content(page_id)
    
    if not chunks:
        print("❌ No indexed content found. Run indexer first.\n")
        return {'status': 'error', 'message': 'No content indexed'}
    
    # Step 2: Generate AI summary
    summary = generate_summary_with_rag(page_title, chunks, has_changes, change_summary)
    
    # Step 3: Format HTML email
    page_url = f"https://eaton-corp.atlassian.net/wiki/spaces/CIPPMOPF/pages/{page_id}"
    
    html = format_email_html(
        page_title=page_title,
        page_url=page_url,
        version=version,
        summary=summary,
        chunks=chunks,
        has_changes=has_changes,
        change_summary=change_summary
    )
    
    # Step 4: Save outputs
    os.makedirs("data/emails", exist_ok=True)
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    
    html_file = f"data/emails/digest_{page_id}_v{version}_{timestamp}.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    json_file = f"data/emails/digest_{page_id}_v{version}_{timestamp}.json"
    with open(json_file, 'w') as f:
        json.dump({
            'page_id': page_id,
            'page_title': page_title,
            'version': version,
            'has_changes': has_changes,
            'change_summary': change_summary,
            'summary': summary,
            'generated_at': datetime.utcnow().isoformat(),
            'chunks_count': len(chunks)
        }, f, indent=2)
    
    print("="*70)
    print("EMAIL DIGEST COMPLETE")
    print("="*70)
    print(f"📧 HTML: {html_file}")
    print(f"📄 JSON: {json_file}")
    print(f"📊 Content: {len(chunks)} chunks indexed")
    print("="*70 + "\n")
    
    return {
        'status': 'success',
        'html_file': html_file,
        'json_file': json_file,
        'chunks_count': len(chunks)
    }


if __name__ == "__main__":
    # Test with ProPM page
    result = generate_page_summary_email(
        page_id="164168599",
        page_title="ProPM Roles & Responsibilities",
        version=11,
        has_changes=False,
        change_summary="No changes"
    )
    
    print(f"\n✅ Test email generated: {result['html_file']}")
