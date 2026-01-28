"""
Image Description Generator using GPT-4o Vision
Specialized prompts for flowcharts, tables, diagrams, and screenshots
"""

import os
import json
import base64
from pathlib import Path
from dotenv import load_dotenv
from openai import AzureOpenAI

# Load environment variables
load_dotenv()

# Azure OpenAI configuration
client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
)

DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")


# Specialized prompts for different image types
PROMPTS = {
    "flowchart": """You are an expert at analyzing flowcharts and process diagrams.
Analyze this flowchart/process diagram and provide a detailed description including:

1. **Overview**: What is this flowchart about? What process does it represent?
2. **Key Components/Nodes**: List all the main boxes, shapes, or entities shown
3. **Flow/Connections**: Describe how the elements are connected and the direction of flow
4. **Roles/Actors**: If there are people icons or role labels, list them and their position in the flow
5. **Phases/Stages**: If the diagram shows phases or stages, describe each one
6. **Key Labels/Text**: Extract all important text labels visible in the diagram
7. **Relationships**: Describe the relationships between different components

Format your response as structured text that captures all the information someone would need to understand this flowchart without seeing it.""",

    "table": """You are an expert at extracting and describing tabular data.
Analyze this table/matrix and provide:

1. **Table Title/Purpose**: What is this table about?
2. **Column Headers**: List all column headers from left to right
3. **Row Headers**: List all row headers/labels from top to bottom
4. **Data Content**: Describe the content in the cells, especially any patterns or key values
5. **Legend/Key**: If there's a legend (like R=Responsible, S=Support), include it
6. **Key Insights**: What are the main takeaways from this table?
7. **Notable Cells**: Highlight any cells with special formatting or important values

If this is a RACI matrix or responsibility assignment matrix, clearly identify:
- Who is Responsible (R) for each task
- Who Supports (S) 
- Who is Informed (I)
- Who is Consulted (C)

Format the extracted data in a clear, searchable text format.""",

    "screenshot": """You are an expert at describing UI screenshots and application interfaces.
Analyze this screenshot and describe:

1. **Application/Context**: What application or interface is this from?
2. **Main Content**: What information is being displayed?
3. **Key Data Fields**: List all visible labels and their values
4. **Tables/Lists**: If there are data tables, extract the headers and sample data
5. **Actions/Buttons**: Note any visible buttons or actionable elements
6. **Key Information**: What is the most important information shown?

Provide a detailed description that captures all the textual and data content visible in the screenshot.""",

    "diagram": """You are an expert at analyzing technical and business diagrams.
Analyze this diagram and provide:

1. **Diagram Type**: What kind of diagram is this (architecture, organizational, conceptual, etc.)?
2. **Main Subject**: What is the central topic or system being depicted?
3. **Components**: List all major components, boxes, or elements
4. **Relationships**: Describe how components are connected or related
5. **Hierarchy**: If there's a hierarchy, describe the levels
6. **Labels/Annotations**: Extract all text labels and annotations
7. **Color Coding**: If colors have meaning, describe what they represent
8. **Key Takeaways**: Summarize the main message or purpose of this diagram

Format your response to capture the complete information content of this diagram.""",

    "general": """Analyze this image in detail and provide a comprehensive description including:

1. **Image Type**: What kind of image is this (diagram, chart, screenshot, photo, etc.)?
2. **Main Content**: What is the primary subject or information shown?
3. **Text Content**: Extract all visible text, labels, and annotations
4. **Visual Elements**: Describe shapes, colors, icons, and their arrangement
5. **Data/Information**: If there's data presented, describe or extract it
6. **Context**: What context or purpose does this image serve?
7. **Key Details**: Note any important details that would help understand this image

Provide a thorough description that would allow someone to understand the image content without seeing it."""
}


def encode_image_to_base64(image_path: str) -> str:
    """Read image file and encode to base64"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def detect_image_type(filename: str, context: str = "") -> str:
    """
    Detect the likely type of image based on filename and context.
    Returns: 'flowchart', 'table', 'screenshot', 'diagram', or 'general'
    """
    filename_lower = filename.lower()
    context_lower = context.lower() if context else ""
    
    # Check for table indicators
    table_keywords = ['table', 'matrix', 'raci', 'responsibility', 'grid', 'spreadsheet']
    if any(kw in filename_lower or kw in context_lower for kw in table_keywords):
        return "table"
    
    # Check for flowchart indicators
    flow_keywords = ['flow', 'process', 'workflow', 'pipeline', 'sequence']
    if any(kw in filename_lower or kw in context_lower for kw in flow_keywords):
        return "flowchart"
    
    # Check for screenshot indicators
    screenshot_keywords = ['screenshot', 'screen', 'email', 'ui', 'interface', 'app']
    if any(kw in filename_lower or kw in context_lower for kw in screenshot_keywords):
        return "screenshot"
    
    # Check for diagram indicators
    diagram_keywords = ['diagram', 'architecture', 'structure', 'org', 'hierarchy']
    if any(kw in filename_lower or kw in context_lower for kw in diagram_keywords):
        return "diagram"
    
    # Default to general
    return "general"


def describe_image(image_path: str, image_type: str = None, context: str = "") -> dict:
    """
    Generate a detailed description of an image using GPT-4o Vision.
    
    Args:
        image_path: Path to the image file
        image_type: Type of image ('flowchart', 'table', 'screenshot', 'diagram', 'general')
                   If None, will auto-detect
        context: Additional context about the image (e.g., surrounding text)
    
    Returns:
        dict with 'description', 'image_type', 'success', 'error'
    """
    try:
        # Validate file exists
        if not os.path.exists(image_path):
            return {"success": False, "error": f"File not found: {image_path}"}
        
        # Auto-detect image type if not provided
        filename = os.path.basename(image_path)
        if image_type is None:
            image_type = detect_image_type(filename, context)
        
        # Get the appropriate prompt
        prompt = PROMPTS.get(image_type, PROMPTS["general"])
        
        # Add context if provided
        if context:
            prompt += f"\n\nAdditional context about this image:\n{context}"
        
        # Encode image
        base64_image = encode_image_to_base64(image_path)
        
        # Determine media type
        ext = Path(image_path).suffix.lower()
        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }.get(ext, "image/png")
        
        # Call GPT-4o Vision
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{base64_image}",
                                "detail": "high"  # Use high detail for complex diagrams/tables
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000,
            temperature=0.3  # Lower temperature for more consistent descriptions
        )
        
        description = response.choices[0].message.content
        
        return {
            "success": True,
            "description": description,
            "image_type": image_type,
            "tokens_used": response.usage.total_tokens if response.usage else None
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "image_type": image_type
        }


def describe_image_from_url(image_url: str, image_type: str = None, context: str = "") -> dict:
    """
    Generate a detailed description of an image from URL using GPT-4o Vision.
    
    Args:
        image_url: URL of the image
        image_type: Type of image ('flowchart', 'table', 'screenshot', 'diagram', 'general')
                   If None, will auto-detect
        context: Additional context about the image (e.g., surrounding text, alt_text)
    
    Returns:
        dict with 'description', 'image_type', 'success', 'error'
    """
    try:
        # Auto-detect image type from URL and context
        filename = image_url.split('/')[-1].split('?')[0]  # Extract filename from URL
        if image_type is None:
            image_type = detect_image_type(filename, context)
        
        # Get the appropriate prompt
        prompt = PROMPTS.get(image_type, PROMPTS["general"])
        
        # Add context if provided
        if context:
            prompt += f"\n\nAdditional context about this image:\n{context}"
        
        # Call GPT-4o Vision with URL directly
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000,
            temperature=0.3
        )
        
        description = response.choices[0].message.content
        
        return {
            "success": True,
            "description": description,
            "image_type": image_type,
            "tokens_used": response.usage.total_tokens if response.usage else None
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "image_type": image_type
        }


def describe_images_in_document(document_json_path: str, update_document: bool = True) -> dict:
    """
    Process all images in a document.json and add descriptions.
    
    Args:
        document_json_path: Path to the document.json file
        update_document: If True, update the document.json with descriptions
    
    Returns:
        dict with results for each image
    """
    doc_path = Path(document_json_path)
    
    # Load document
    with open(doc_path, 'r', encoding='utf-8') as f:
        document = json.load(f)
    
    base_folder = doc_path.parent
    results = {}
    total_tokens = 0
    
    print(f"\n{'='*70}")
    print(f"Processing images in: {document['metadata']['title']}")
    print(f"{'='*70}")
    
    # Process each content block
    for block in document['content_blocks']:
        if block['type'] == 'image':
            # Handle both local files and external URLs
            has_local = block.get('local_path')
            has_external = block.get('external_url')
            
            if not has_local and not has_external:
                continue
                
            filename = block.get('filename', 'unknown')
            index = block.get('index', 0)
            
            print(f"\n📷 [{index:02d}] Processing: {filename}")
            
            # Get context from surrounding blocks
            context_parts = []
            
            # Look for text/heading before this image
            for prev_block in document['content_blocks']:
                if prev_block['index'] < index and prev_block['index'] >= index - 2:
                    if prev_block['type'] == 'heading':
                        context_parts.append(f"Section: {prev_block['content']}")
                    elif prev_block['type'] == 'text':
                        context_parts.append(prev_block['content'][:200])
            
            # Add alt_text as context if available
            if block.get('alt_text'):
                context_parts.append(f"Alt text: {block['alt_text']}")
            
            context = " | ".join(context_parts) if context_parts else ""
            
            # Generate description based on source type
            if has_local:
                image_path = base_folder / block['local_path']
                result = describe_image(str(image_path), context=context)
            else:
                # External URL - use the URL directly
                print(f"   🌐 External URL: {has_external[:60]}...")
                result = describe_image_from_url(has_external, context=context)
            
            if result['success']:
                block['description'] = result['description']
                block['description_type'] = result['image_type']
                total_tokens += result.get('tokens_used', 0)
                
                print(f"   ✅ Described as: {result['image_type']}")
                print(f"   📝 Preview: {result['description'][:100]}...")
            else:
                print(f"   ❌ Error: {result.get('error', 'Unknown error')}")
            
            results[filename] = result
    
    # Update document with descriptions
    if update_document:
        document['metadata']['images_described'] = True
        document['metadata']['description_tokens_used'] = total_tokens
        
        with open(doc_path, 'w', encoding='utf-8') as f:
            json.dump(document, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Updated: {doc_path}")
        
        # Also update the readable text file
        readable_path = base_folder / "content_readable.txt"
        if readable_path.exists():
            update_readable_file(document, readable_path)
            print(f"✅ Updated: {readable_path}")
    
    print(f"\n📊 Total tokens used: {total_tokens:,}")
    
    return {
        "images_processed": len(results),
        "total_tokens": total_tokens,
        "results": results
    }


def update_readable_file(document: dict, readable_path: Path):
    """Update the human-readable text file with image descriptions"""
    
    with open(readable_path, 'w', encoding='utf-8') as f:
        meta = document['metadata']
        
        f.write(f"{'='*70}\n")
        f.write(f"TITLE: {meta['title']}\n")
        f.write(f"PAGE ID: {meta['page_id']}\n")
        f.write(f"SPACE: {meta['space_key']}\n")
        f.write(f"VERSION: {meta['version']}\n")
        f.write(f"LAST MODIFIED: {meta['last_modified']}\n")
        f.write(f"{'='*70}\n\n")
        
        for block in document['content_blocks']:
            block_type = block['type']
            idx = block['index']
            
            if block_type == 'heading':
                level = block['level']
                f.write(f"\n{'#' * level} {block['content']}\n\n")
            
            elif block_type == 'text':
                f.write(f"{block['content']}\n\n")
            
            elif block_type == 'image':
                f.write(f"\n[IMAGE {idx}]: {block.get('filename', 'unknown')}\n")
                if block.get('local_path'):
                    f.write(f"  File: {block['local_path']}\n")
                elif block.get('external_url'):
                    f.write(f"  URL: {block['external_url'][:80]}...\n")
                
                # Add description if available
                if block.get('description'):
                    f.write(f"\n  📝 IMAGE DESCRIPTION ({block.get('description_type', 'general')}):\n")
                    f.write(f"  {'-'*60}\n")
                    # Indent each line of description
                    for line in block['description'].split('\n'):
                        f.write(f"  {line}\n")
                    f.write(f"  {'-'*60}\n")
                f.write("\n")
            
            elif block_type == 'list':
                list_type = block.get('list_type', 'unordered')
                for i, item in enumerate(block.get('items', []), 1):
                    prefix = f"{i}." if list_type == 'ordered' else "•"
                    f.write(f"  {prefix} {item}\n")
                f.write("\n")
            
            elif block_type == 'table':
                f.write("\n[TABLE]\n")
                for row in block.get('rows', []):
                    f.write(f"  | {' | '.join(str(cell) for cell in row)} |\n")
                f.write("\n")


def main():
    """Main entry point - process the ProPM Roles & Responsibilities page"""
    
    print("=" * 70)
    print("GPT-4o IMAGE DESCRIPTION GENERATOR")
    print("=" * 70)
    
    # Target document
    doc_path = Path("data/pages/CIPPMOPF/164168599/document.json")
    
    if not doc_path.exists():
        print(f"❌ Document not found: {doc_path}")
        print("Run confluence_content_extractor.py first!")
        return
    
    # Process images
    results = describe_images_in_document(str(doc_path))
    
    print("\n" + "=" * 70)
    print("PROCESSING COMPLETE")
    print("=" * 70)
    print(f"✅ Images processed: {results['images_processed']}")
    print(f"📊 Total tokens: {results['total_tokens']:,}")


if __name__ == "__main__":
    main()
