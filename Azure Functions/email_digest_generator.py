"""
Email Digest Generator
Creates beautiful HTML email summaries using indexed content and GPT-4o
"""

import os
import sys
import json
import re
import ssl
import httpx
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

load_dotenv()

# Disable SSL verification for corporate proxy
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Create SSL context that doesn't verify certificates (for corporate proxy)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Azure OpenAI configuration with timeout
openai_client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
    http_client=httpx.Client(verify=False, timeout=120.0)  # 2 minute timeout
)

# Azure AI Search configuration
SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")
SEARCH_INDEX_NAME = "confluence-rag-index"

# Azure Blob Storage
BLOB_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
BLOB_ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")

# Embedding configuration with timeout
embedding_client = AzureOpenAI(
    azure_endpoint=os.getenv("FOUNDRY_EMBEDDING_ENDPOINT"),
    api_key=os.getenv("FOUNDRY_EMBEDDING_API_KEY"),
    api_version="2024-02-01",
    http_client=httpx.Client(verify=False, timeout=60.0)  # 1 minute timeout
)

MODEL = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
EMBEDDING_MODEL = os.getenv("FOUNDRY_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")


def get_blob_service_client():
    """Get blob service client with SSL verification disabled for corporate proxy"""
    from azure.core.pipeline.transport import RequestsTransport
    import requests
    
    # Create a session that doesn't verify SSL
    session = requests.Session()
    session.verify = False
    
    return BlobServiceClient(
        account_url=f"https://{BLOB_ACCOUNT_NAME}.blob.core.windows.net",
        credential=BLOB_ACCOUNT_KEY,
        transport=RequestsTransport(session=session),
        max_single_put_size=4*1024*1024,  # 4MB
        retry_total=1,  # Minimal retries
        retry_connect=1,
        retry_read=1
    )


def upload_email_to_blob(page_id, version, html_content, metadata):
    """
    Upload email digest to Azure Blob Storage for email delivery system.
    
    Structure:
    confluence-emails/
    ├── {page_id}/
    │   ├── latest/
    │   │   ├── digest.html      (always current version)
    │   │   └── metadata.json
    │   └── archive/
    │       └── digest_v{version}_{timestamp}.html
    
    Returns: URL to the latest email blob
    """
    EMAIL_CONTAINER = os.getenv("EMAIL_CONTAINER", "confluence-emails")
    
    try:
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(EMAIL_CONTAINER)
        
        # Create container if it doesn't exist
        try:
            container_client.create_container()
            print(f"   📁 Created container: {EMAIL_CONTAINER}")
        except Exception:
            pass  # Container already exists
        
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        
        # 1. Upload to latest/ (overwrite) - with short timeout
        latest_html_blob = f"{page_id}/latest/digest.html"
        try:
            container_client.upload_blob(
                name=latest_html_blob,
                data=html_content.encode('utf-8'),
                content_settings=ContentSettings(content_type="text/html"),
                overwrite=True,
                timeout=10  # 10 second timeout
            )
        except Exception as e:
            print(f"   ⚠️ Latest blob upload skipped: {str(e)[:50]}")
        
        # 2. Upload metadata to latest/
        latest_meta_blob = f"{page_id}/latest/metadata.json"
        try:
            container_client.upload_blob(
                name=latest_meta_blob,
                data=json.dumps(metadata, indent=2).encode('utf-8'),
                content_settings=ContentSettings(content_type="application/json"),
                overwrite=True,
                timeout=10
            )
        except Exception as e:
            print(f"   ⚠️ Metadata blob upload skipped: {str(e)[:50]}")
        
        # 3. Archive this version (optional - skip on error)
        archive_blob = f"{page_id}/archive/digest_v{version}_{timestamp}.html"
        try:
            container_client.upload_blob(
                name=archive_blob,
                data=html_content.encode('utf-8'),
                content_settings=ContentSettings(content_type="text/html"),
                overwrite=True,
                timeout=10
            )
        except Exception as e:
            print(f"   ⚠️ Archive blob upload skipped: {str(e)[:50]}")
        
        # Return URL to latest email
        blob_url = f"https://{BLOB_ACCOUNT_NAME}.blob.core.windows.net/{EMAIL_CONTAINER}/{latest_html_blob}"
        return blob_url
        
    except Exception as e:
        print(f"   ⚠️ Email blob upload failed (non-blocking): {str(e)[:80]}")
        return None  # Don't raise - continue with email sending


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
    Uses teal/green color scheme matching the email template.
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
                # Prominent styling for key headers - teal theme
                formatted_parts.append(f'<p style="margin: 18px 0 8px 0; padding: 8px 12px; background-color: #e0f2f1; border-left: 4px solid #00796b; border-radius: 0 4px 4px 0;"><strong style="color: #00796b; font-size: 15px;">{line}</strong></p>')
            else:
                formatted_parts.append(f'<p style="margin: 15px 0 5px 0;"><strong style="color: #00796b;">{line}</strong></p>')
        
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
    Format beautiful HTML email using professional teal/green template
    """
    # Format summary using Agent 2 (HTML Formatter)
    formatted_summary = agent_html_formatter(summary)
    
    # Build change notice section
    if has_changes and change_summary and change_summary != "No changes":
        change_notice = f"""
                    <!-- Change Notice -->
                    <tr>
                        <td style="padding: 0 30px 20px 30px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-radius: 8px; overflow: hidden; background-color: #fff8e1; border: 2px solid #ffd54f;">
                                <tr>
                                    <td style="padding: 15px; font-size: 14px; color: #f57f17; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
                                        <strong style="display: block; margin-bottom: 4px;">⚡ Recent Changes</strong>
                                        {change_summary}
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
        """
    else:
        change_notice = """
                    <!-- No Changes Notice -->
                    <tr>
                        <td style="padding: 0 30px 20px 30px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-radius: 8px; overflow: hidden; background-color: #f1f8f6; border: 1px solid #b2dfdb;">
                                <tr>
                                    <td style="padding: 12px 15px; font-size: 13px; color: #00796b; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
                                        ℹ️ No changes since last version
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
        """
    
    # Build content preview - show sections
    content_items = ""
    for chunk in chunks[:6]:  # Show first 6 sections
        content_text = chunk.get('content_text', '')
        first_line = content_text.split('\n')[0].strip('#').strip()[:60]
        if first_line:
            content_items += f"<li style='margin: 4px 0;'>{first_line}</li>"
    
    if len(chunks) > 6:
        content_items += f"<li style='margin: 4px 0; font-style: italic;'>...and {len(chunks) - 6} more sections</li>"
    
    # Extract space key from URL
    space_key = "CIPPMOPF"
    if "/spaces/" in page_url:
        try:
            space_key = page_url.split("/spaces/")[1].split("/")[0]
        except:
            pass
    
    html = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>{page_title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
    <!-- Main Container -->
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f5f5f5; padding: 20px 0;">
        <tr>
            <td align="center">
                <!-- Email Content -->
                <table border="0" cellpadding="0" cellspacing="0" width="750" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08);">
                    
                    <!-- Accent Bar -->
                    <tr>
                        <td bgcolor="#00796b" style="background-color: #00796b; padding: 4px 0;"></td>
                    </tr>

                    <!-- Header -->
                    <tr>
                        <td style="padding: 30px 30px 10px 30px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td>
                                        <div style="display: inline-block; background-color: #00796b; color: #ffffff; padding: 4px 12px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
                                            Weekly Update
                                        </div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <tr>
                        <td style="padding: 0 30px 20px 30px;">
                            <h1 style="margin: 0; color: #004d40; font-size: 26px; font-weight: 600; line-height: 1.3; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
                                {page_title}
                            </h1>
                        </td>
                    </tr>

                    <!-- Meta Information Cards -->
                    <tr>
                        <td style="padding: 0 30px 20px 30px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td width="48%" style="vertical-align: top;">
                                        <table border="0" cellpadding="12" cellspacing="0" width="100%" style="background-color: #f1f8f6; border-radius: 8px;">
                                            <tr>
                                                <td>
                                                    <div style="font-size: 11px; color: #00796b; font-weight: 600; text-transform: uppercase; margin-bottom: 4px; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">Generated</div>
                                                    <div style="font-size: 13px; color: #004d40; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">{datetime.utcnow().strftime('%B %d, %Y at %H:%M UTC')}</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                    <td width="4%"></td>
                                    <td width="48%" style="vertical-align: top;">
                                        <table border="0" cellpadding="12" cellspacing="0" width="100%" style="background-color: #f1f8f6; border-radius: 8px;">
                                            <tr>
                                                <td>
                                                    <div style="font-size: 11px; color: #00796b; font-weight: 600; text-transform: uppercase; margin-bottom: 4px; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">Version</div>
                                                    <div style="font-size: 13px; color: #004d40; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">v{version}</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    {change_notice}

                    <!-- Executive Summary -->
                    <tr>
                        <td style="padding: 0 30px 20px 30px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td style="padding: 0 0 12px 0;">
                                        <h2 style="margin: 0; color: #00796b; font-size: 18px; font-weight: 600; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
                                            📝 Executive Summary
                                        </h2>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 18px; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; font-size: 14px; color: #004d40; line-height: 1.7; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
                                        {formatted_summary}
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- CTA Button - Email Safe (no gradients) -->
                    <tr>
                        <td style="padding: 0 30px 20px 30px;">
                            <table border="0" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td align="center" bgcolor="#00796b" style="border-radius: 8px; background-color: #00796b;">
                                        <a href="{page_url}" target="_blank" style="font-size: 15px; font-weight: 600; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 8px; display: inline-block; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #00796b;">
                                            Open in Confluence →
                                        </a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Content Preview -->
                    <tr>
                        <td style="padding: 0 30px 20px 30px;">
                            <table border="0" cellpadding="18" cellspacing="0" width="100%" style="background-color: #ffffff; border-radius: 8px; border: 1px solid #e0e0e0;">
                                <tr>
                                    <td style="font-size: 14px; color: #333333; line-height: 1.7; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
                                        <h3 style="margin: 0 0 10px 0; color: #00796b; font-size: 15px; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">📄 Page Sections</h3>
                                        <ul style="margin: 0; padding-left: 20px;">
                                            {content_items}
                                        </ul>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 30px 30px 30px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td style="border-top: 1px solid #e0e0e0; padding-top: 20px; text-align: center;">
                                        <div style="font-size: 12px; color: #757575; line-height: 1.6; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
                                            This is an automated digest from Confluence
                                        </div>
                                        <div style="font-size: 12px; margin-top: 8px; font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
                                            <a href="{page_url}" style="color: #00796b; text-decoration: none; font-weight: 500;">View {page_title} Online</a>
                                            <span style="color: #bdbdbd; margin: 0 8px;">|</span>
                                            <a href="#" style="color: #00796b; text-decoration: none; font-weight: 500;">Preferences</a>
                                        </div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
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
    
    # Step 4: Save outputs locally
    os.makedirs("data/emails", exist_ok=True)
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    
    html_file = f"data/emails/digest_{page_id}_v{version}_{timestamp}.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    json_file = f"data/emails/digest_{page_id}_v{version}_{timestamp}.json"
    metadata = {
        'page_id': page_id,
        'page_title': page_title,
        'version': version,
        'has_changes': has_changes,
        'change_summary': change_summary,
        'summary': summary,
        'generated_at': datetime.utcnow().isoformat(),
        'chunks_count': len(chunks)
    }
    with open(json_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Step 5: Upload to Azure Blob Storage for email delivery
    blob_url = None
    try:
        blob_url = upload_email_to_blob(page_id, version, html, metadata)
        print(f"☁️  Uploaded to Blob: {blob_url}")
    except Exception as e:
        print(f"⚠️  Blob upload failed (continuing): {e}")
    
    print("="*70)
    print("EMAIL DIGEST COMPLETE")
    print("="*70)
    print(f"📧 HTML: {html_file}")
    print(f"📄 JSON: {json_file}")
    if blob_url:
        print(f"☁️  Blob: {blob_url}")
    print(f"📊 Content: {len(chunks)} chunks indexed")
    print("="*70 + "\n")
    
    return {
        'status': 'success',
        'html_file': html_file,
        'json_file': json_file,
        'blob_url': blob_url,
        'chunks_count': len(chunks),
        'html_content': html,
        'metadata': metadata
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
