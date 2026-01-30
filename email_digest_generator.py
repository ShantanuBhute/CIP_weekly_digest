"""
Email Digest Generator
Creates beautiful HTML email summaries using indexed content and GPT-4o
"""

import os
import sys
import json
import re
import httpx
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobServiceClient

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

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
SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "confluence-rag-index-v2")

# Azure Blob Storage
BLOB_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
BLOB_ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")

# Embedding configuration
embedding_client = AzureOpenAI(
    azure_endpoint=os.getenv("FOUNDRY_EMBEDDING_ENDPOINT"),
    api_key=os.getenv("FOUNDRY_EMBEDDING_API_KEY"),
    api_version="2024-02-01",
    http_client=httpx.Client(verify=False)
)

MODEL = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
EMBEDDING_MODEL = os.getenv("FOUNDRY_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")


def get_blob_service_client():
    """Get blob service client"""
    return BlobServiceClient(
        account_url=f"https://{BLOB_ACCOUNT_NAME}.blob.core.windows.net",
        credential=BLOB_ACCOUNT_KEY
    )


def get_image_descriptions_from_document(page_id, space_key="CIPPMOPF"):
    """
    Get image descriptions from the current local document.json
    Returns dict: {filename: description}
    """
    doc_path = Path(f"data/pages/{space_key}/{page_id}/document.json")
    if not doc_path.exists():
        return {}
    
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
        
        descriptions = {}
        for block in doc.get('content_blocks', []):
            if block.get('type') == 'image':
                filename = block.get('filename', '')
                desc = block.get('description', '')
                if filename and desc:
                    # Get first 100 chars of description
                    short_desc = desc[:150].split('\n')[0]
                    descriptions[filename] = short_desc
        return descriptions
    except Exception as e:
        print(f"   ⚠️ Could not load image descriptions: {e}")
        return {}


def get_previous_image_descriptions(page_id, previous_version, space_key="CIPPMOPF"):
    """
    Get image descriptions from the previous version's document.json in blob storage
    Returns dict: {filename: description}
    """
    if not previous_version:
        return {}
    
    try:
        blob_service = get_blob_service_client()
        container = blob_service.get_container_client("confluence-rag")
        
        # Try to get previous version's document.json
        blob_path = f"{space_key}/{page_id}/v{previous_version}/document.json"
        blob_client = container.get_blob_client(blob_path)
        
        content = blob_client.download_blob().readall()
        doc = json.loads(content)
        
        descriptions = {}
        for block in doc.get('content_blocks', []):
            if block.get('type') == 'image':
                filename = block.get('filename', '')
                desc = block.get('description', '')
                if filename and desc:
                    short_desc = desc[:150].split('\n')[0]
                    descriptions[filename] = short_desc
        return descriptions
    except Exception as e:
        # Silently fail - previous version might not exist
        return {}


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


def agent_content_writer(page_title, chunks, has_changes, change_summary):
    """
    AGENT 1: Content Writer
    Analyzes RAG context and produces structured text summary.
    Focuses purely on content - no HTML formatting.
    """
    print(f"🤖 Agent 1 (Content Writer): Analyzing content...\n")
    
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
    
    # Then add text content (excluding image descriptions which are handled above)
    context += "=== TEXT CONTENT ===\n"
    for chunk in chunks:
        content_text = chunk.get('content_text', '')
        if content_text:
            # Remove image descriptions from content_text to avoid duplication
            # Image descriptions start with "IMAGE (" and are formatted descriptions
            import re
            
            # Strategy: Extract text that is NOT part of image descriptions
            # Image descriptions are structured with ### headers and numbered lists
            lines = content_text.split('\n')
            clean_lines = []
            in_image_description = False
            
            for line in lines:
                # Detect start of image description
                if line.strip().startswith('IMAGE (') or line.strip().startswith('📷 IMAGE'):
                    in_image_description = True
                    continue
                
                # Image descriptions typically have these patterns
                if in_image_description:
                    if line.strip().startswith('### Comprehensive') or \
                       line.strip().startswith('1. **Image Type**') or \
                       line.strip().startswith('2. **Main Content**') or \
                       line.strip().startswith('**Image Type**'):
                        continue
                    # Check if we've exited the image description (blank line + non-indented content)
                    if line.strip() == '':
                        continue
                    # Numbered items (1., 2., etc.) or indented text are likely image descriptions
                    if re.match(r'^\s*\d+\.\s+\*\*', line) or line.startswith('   '):
                        continue
                    # Lines like "### Summary:" are part of image description
                    if line.strip().startswith('### ') and any(kw in line for kw in ['Summary', 'Key Details', 'Notes']):
                        continue
                    # If we get a line that looks like regular content, we've exited
                    if len(line.strip()) > 20 and not line.startswith('   ') and not line.startswith('*') and not line.startswith('-'):
                        in_image_description = False
                        clean_lines.append(line)
                else:
                    # Not in image description - keep the line
                    clean_lines.append(line)
            
            clean_text = '\n'.join(clean_lines).strip()
            if clean_text:
                context += f"{clean_text[:5000]}\n\n"
    
    # Build prompt for dual audience (technical + managerial)
    prompt = f"""Create a CONCISE executive email digest for a Confluence page.

Page: {page_title}

Page Content:
{context[:15000]}

INSTRUCTIONS:
Write a professional email in natural flowing prose. Keep it crisp and scannable.

YOU MUST USE EXACTLY THESE SECTION HEADERS (on their own line):

Overview:
2 sentences max - what this page is about.

Key Insights:
1-2 short paragraphs weaving together ALL information from the page (text, diagrams, matrices, screenshots). Do NOT use "Image 1/2" labels - integrate naturally.

For Technical Teams:
1 paragraph on processes, workflows, RACI assignments, system details. Use bullets ONLY for 4+ role assignments.

For Managers & Stakeholders:
1 paragraph on business impact and governance. Keep it brief.

CRITICAL FORMAT RULES:
- Each section header MUST be on its own line followed by a newline
- Use EXACTLY these headers: "Overview:", "Key Insights:", "For Technical Teams:", "For Managers & Stakeholders:"
- Content for each section starts on the NEXT line after the header

RULES:
- Include ALL content from EVERY 📷 IMAGE section - integrated naturally
- Include ALL text sections - even if they seem unrelated to the main topic (e.g., news about companies, random paragraphs)
- If there's content about Tesla, BYD, Naruto, or any other topic - IT MUST be mentioned
- Be CONCISE - every sentence must add value
- Minimize bullets - use flowing prose
- NO markdown formatting (no **, no ##, etc.)
- Do NOT fabricate
- If page has limited content, say so

Sign off as:
Best regards,
CIP Weekly Digest"""
    
    try:
        response = openai_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": """You write CONCISE executive summaries in polished, flowing prose.

WRITING STYLE:
- Be CRISP - every sentence must earn its place
- Write smooth paragraphs, NOT bullet-heavy lists
- NEVER use "Image 1", "Image 2" - integrate insights naturally
- Bullets ONLY for 4+ specific items (like RACI roles)
- Sound like a polished executive briefing

CONTENT RULES:
1. Include insights from EVERY 📷 IMAGE section - integrated naturally
2. Include ALL text content - NOTHING can be skipped, even if it seems off-topic
3. If there's a section about Tesla, Naruto, or any other topic - IT MUST appear in the summary
4. NEVER FABRICATE - only information explicitly in the content
3. NEVER FABRICATE - only information explicitly in the content

HANDLING VISUALS:
- Integrate image insights into your paragraphs seamlessly
- Example: "The accountability structure assigns Portfolio Manager as responsible for..." (not "Image 1 shows...")
- For RACI: mention key role assignments concisely
- For screenshots: note what system/data it shows

FORMATTING:
- Paragraphs primarily, minimal bullets
- NO markdown
- Sign off as "CIP Weekly Digest"""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1600  # Reduced for crisper output
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
        
        # Ensure section headers are on their own lines (for consistent HTML formatting)
        import re
        # Fix headers that might be inline: "For Technical Teams: The RACI..." -> "For Technical Teams:\nThe RACI..."
        for header in ['Overview:', 'Key Insights:', 'For Technical Teams:', 'For Managers & Stakeholders:', 'For Managers:']:
            # Match header followed by non-newline content
            pattern = re.escape(header) + r'[ ]*([^\n])'
            replacement = header + r'\n\1'
            summary = re.sub(pattern, replacement, summary)
        
        # Extract token usage
        usage = response.usage
        print(f"✅ Agent 1 complete: Content summary generated")
        print(f"   Tokens: {usage.total_tokens} (prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens})\n")
        
        return summary
    
    except Exception as e:
        print(f"❌ Agent 1 failed: {e}\n")
        return f"Error generating summary. Please review the page directly."


def agent_change_summarizer(change_summary, page_id=None, previous_version=None):
    """
    AGENT 1.5: Change Summarizer
    Takes raw change data and creates a BRIEF but INFORMATIVE summary.
    Looks up ACTUAL image descriptions from document.json files.
    """
    if not change_summary or change_summary == "No changes":
        return None
    
    print(f"🔄 Agent 1.5 (Change Summarizer): Analyzing changes...\n")
    
    # Get image descriptions from current and previous versions
    current_img_descs = {}
    previous_img_descs = {}
    
    if page_id:
        current_img_descs = get_image_descriptions_from_document(page_id)
        if current_img_descs:
            print(f"   📷 Found {len(current_img_descs)} image descriptions from current version")
        
        if previous_version:
            previous_img_descs = get_previous_image_descriptions(page_id, previous_version)
            if previous_img_descs:
                print(f"   📷 Found {len(previous_img_descs)} image descriptions from previous version")
    
    # Enrich change_summary with actual image descriptions
    enriched_summary = change_summary
    
    # Replace image references with actual descriptions
    # Pattern: NEW IMAGE ADDED: [IMAGE_ATTACHMENT: filename.png]
    for match in re.finditer(r'NEW IMAGE ADDED:.*?\[IMAGE_(?:ATTACHMENT|EXTERNAL):\s*([^\]]+)\]', change_summary):
        filename = match.group(1).strip()
        # Extract just the filename from URLs
        if '/' in filename:
            filename = filename.split('/')[-1]
        
        if filename in current_img_descs:
            desc = current_img_descs[filename]
            enriched_summary = enriched_summary.replace(
                match.group(0), 
                f'NEW IMAGE ADDED: "{desc}"'
            )
    
    # Pattern: IMAGE REMOVED: [IMAGE_ATTACHMENT: filename.png]
    for match in re.finditer(r'IMAGE REMOVED:.*?\[IMAGE_(?:ATTACHMENT|EXTERNAL):\s*([^\]]+)\]', change_summary):
        filename = match.group(1).strip()
        if '/' in filename:
            filename = filename.split('/')[-1]
        
        if filename in previous_img_descs:
            desc = previous_img_descs[filename]
            enriched_summary = enriched_summary.replace(
                match.group(0), 
                f'IMAGE REMOVED: "{desc}"'
            )
    
    try:
        response = openai_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": """You summarize document changes in 2-3 SHORT sentences.

RULES:
- Be BRIEF but INFORMATIVE
- For images: use the provided description (in quotes) to explain what the image shows
- For text: extract just the TOPIC, not full content
- Maximum 3 sentences total

EXAMPLES:
Input: 'NEW IMAGE ADDED: "Shows RACI matrix with role assignments"'
Output: "Added a RACI matrix diagram showing role assignments."

Input: 'IMAGE REMOVED: "Displays process flowchart" | NEW TEXT: "Blade battery..."'
Output: "Removed process flowchart. Added content about blade battery technology."

Be specific about what was ADDED vs REMOVED."""},
                {"role": "user", "content": f"""Summarize these changes in 2-3 informative sentences:

{enriched_summary[:3000]}

Use the descriptions in quotes to explain what images show."""}
            ],
            temperature=0.2,
            max_tokens=150
        )
        
        result = response.choices[0].message.content.strip()
        # Clean up any bullet formatting
        result = result.replace('- ', '').replace('• ', '')
        # Ensure it's not too long
        if len(result) > 300:
            result = result[:300] + "..."
        print(f"✅ Agent 1.5 complete: {result}\n")
        return result
    
    except Exception as e:
        print(f"⚠️ Agent 1.5 failed, using fallback: {e}")
        return "Content has been updated."


def agent_html_formatter(summary):
    """
    AGENT 2: HTML Formatter
    Takes plain text summary from Agent 1 and converts to polished HTML.
    Handles line breaks, paragraph structure, and styling.
    FLAT bullets only - no nesting.
    """
    print(f"🎨 Agent 2 (HTML Formatter): Styling content...")
    # Clean up markdown artifacts
    summary = summary.replace('**', '')
    summary = summary.replace('__', '')
    summary = summary.replace('[Your Name]', 'CIP Weekly Digest')
    summary = summary.replace('[Your Position]', '')
    
    lines = summary.split('\n')
    formatted_parts = []
    in_bullet_list = False
    
    # Key section headers that should be styled prominently
    key_headers = ['For Technical Teams:', 'For Managers & Stakeholders:', 'For Managers:', 
                   'Key Insights:', 'Overview:', 'Technical Teams:', 'Managers & Stakeholders:']
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_bullet_list:
                formatted_parts.append('</ul>')
                in_bullet_list = False
            continue
        
        # Check if it's a KEY section header (bold with colored background)
        is_key_header = any(line.startswith(h.replace(':', '')) or line == h for h in key_headers)
        
        # Check if it's a section header (ends with : and is short)
        if line.endswith(':') and len(line) < 50 and not line.startswith('•'):
            if in_bullet_list:
                formatted_parts.append('</ul>')
                in_bullet_list = False
            
            if is_key_header:
                # Prominent styling for key headers
                formatted_parts.append(f'<p style="margin: 18px 0 8px 0; padding: 8px 12px; background: linear-gradient(90deg, #e8f0fe 0%, #f8f9fa 100%); border-left: 4px solid #1a73e8; border-radius: 0 4px 4px 0;"><strong style="color: #1a73e8; font-size: 15px;">{line}</strong></p>')
            else:
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
            formatted_parts.append(f'<p style="margin: 8px 0; line-height: 1.6;">{line}</p>')
    
    # Close any open list
    if in_bullet_list:
        formatted_parts.append('</ul>')
    
    result = '\n'.join(formatted_parts)
    print(f"✅ Agent 2 complete: HTML formatted\n")
    return result


def format_email_html(page_title, page_url, version, summary, chunks, has_changes, change_summary):
    """
    Format beautiful HTML email
    """
    # Build change summary banner
    # If NO changes → show brief status at top
    # If HAS changes → move detailed updates to bottom
    
    if has_changes and change_summary and change_summary != "No changes":
        # Changes detected - put banner at BOTTOM
        top_status_banner = ""
        bottom_updates_section = f"""
        <h2 style="margin-top: 30px;">📝 Recent Updates</h2>
        <div style="background: #e6f4ea; border-left: 4px solid #34a853; padding: 12px 15px; margin: 15px 0; border-radius: 0 5px 5px 0;">
            <p style="margin: 0; font-size: 14px; color: #333;">{change_summary}</p>
        </div>
        """
    else:
        # No changes - show brief status at top
        top_status_banner = f"""
        <div style="background: #f8f9fa; border-left: 4px solid #9aa0a6; padding: 10px 15px; margin: 15px 0; border-radius: 0 5px 5px 0;">
            <span style="color: #5f6368; font-size: 13px;">ℹ️ No changes since last version</span>
        </div>
        """
        bottom_updates_section = ""
    
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
    
    # Format summary using Agent 2 (HTML Formatter)
    formatted_summary = agent_html_formatter(summary)
    
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
        
        {top_status_banner}
        
        <h2>📝 Executive Summary</h2>
        <div class="summary">
            {formatted_summary}
        </div>
        
        <a href="{page_url}" class="btn">📖 View Full Page in Confluence</a>
        
        <div class="content-preview">
            {content_preview}
        </div>
        
        {bottom_updates_section}
        
    </div>
</body>
</html>"""
    
    return html


def generate_page_summary_email(page_id, page_title, version, has_changes, change_summary, previous_version=None):
    """
    Main function to generate complete email digest using 2-agent architecture.
    
    Agent 1 (Content Writer): Generates structured text summary from RAG context
    Agent 1.5 (Change Summarizer): Simplifies raw change data to human-friendly summary
    Agent 2 (HTML Formatter): Converts text to polished HTML email
    """
    print("\n" + "="*70)
    print("EMAIL DIGEST GENERATION (2-Agent Architecture)")
    print("="*70 + "\n")
    
    # Step 1: Retrieve indexed content
    chunks = retrieve_page_content(page_id)
    
    if not chunks:
        print("❌ No indexed content found. Run indexer first.\n")
        return {'status': 'error', 'message': 'No content indexed'}
    
    # Step 2: Agent 1.5 - Simplify change summary (if there are changes)
    friendly_change_summary = None
    if has_changes and change_summary and change_summary != "No changes":
        friendly_change_summary = agent_change_summarizer(
            change_summary, 
            page_id=page_id, 
            previous_version=previous_version
        )
    
    # Step 3: Agent 1 - Generate content summary
    summary = agent_content_writer(page_title, chunks, has_changes, change_summary)
    
    # Step 4: Agent 2 - Format HTML (called inside format_email_html)
    page_url = f"https://eaton-corp.atlassian.net/wiki/spaces/CIPPMOPF/pages/{page_id}"
    
    html = format_email_html(
        page_title=page_title,
        page_url=page_url,
        version=version,
        summary=summary,
        chunks=chunks,
        has_changes=has_changes,
        change_summary=friendly_change_summary  # Use the simplified version
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
