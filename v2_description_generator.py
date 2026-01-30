"""
V2 Description Generator - GPT-4o Vision with Hash-Based Caching
CRITICAL OPTIMIZATION: Only calls GPT-4o for NEW or CHANGED images.

Cost Impact Analysis:
- GPT-4o Vision: ~$0.05 per image (high detail)
- 10 images per page = $0.50/page/run
- 100 pages = $50/run
- Daily runs = $1,500/month WASTED if images unchanged

V2 Solution:
- Cache descriptions by image content hash
- Same image = same hash = use cached description
- 90%+ cost savings on typical runs
"""

import os
import json
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv
from openai import AzureOpenAI
from v2_storage_manager import V2StorageManager, get_v2_storage_manager

load_dotenv()

# Azure OpenAI configuration
client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
)

DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")


# Specialized prompts (same as v1)
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


class V2DescriptionGenerator:
    """
    GPT-4o Vision description generator with caching.
    Only processes images that don't have cached descriptions.
    """
    
    def __init__(self, storage_manager: V2StorageManager = None):
        self.storage = storage_manager or get_v2_storage_manager()
        self.stats = {
            'from_cache': 0,
            'generated': 0,
            'failed': 0,
            'tokens_used': 0,
            'cost_saved': 0.0  # Estimated
        }
        self.COST_PER_IMAGE = 0.05  # Approximate cost per GPT-4o vision call
    
    @staticmethod
    def detect_image_type(filename: str, context: str = "") -> str:
        """Detect image type from filename and context"""
        filename_lower = filename.lower()
        context_lower = context.lower() if context else ""
        
        # Check for table indicators
        if any(kw in filename_lower or kw in context_lower for kw in ['table', 'matrix', 'raci', 'responsibility', 'grid']):
            return "table"
        
        # Check for flowchart indicators
        if any(kw in filename_lower or kw in context_lower for kw in ['flow', 'process', 'workflow', 'pipeline', 'sequence']):
            return "flowchart"
        
        # Check for screenshot indicators
        if any(kw in filename_lower or kw in context_lower for kw in ['screenshot', 'screen', 'email', 'ui', 'interface']):
            return "screenshot"
        
        # Check for diagram indicators
        if any(kw in filename_lower or kw in context_lower for kw in ['diagram', 'architecture', 'structure', 'org', 'hierarchy']):
            return "diagram"
        
        return "general"
    
    def get_cached_description(
        self,
        space_key: str,
        page_id: str,
        page_title: str,
        image_hash: str
    ) -> Optional[Dict]:
        """
        Check if we have a cached description for this image hash.
        Returns the cached description data if found.
        """
        return self.storage.get_cached_description(
            space_key, page_id, page_title, image_hash
        )
    
    def generate_description(
        self,
        image_path: str = None,
        image_url: str = None,
        image_type: str = None,
        context: str = ""
    ) -> Dict:
        """
        Generate description using GPT-4o Vision.
        Accepts either local path or URL.
        """
        try:
            # Auto-detect image type
            filename = Path(image_path).name if image_path else image_url.split('/')[-1].split('?')[0]
            if image_type is None:
                image_type = self.detect_image_type(filename, context)
            
            # Get prompt
            prompt = PROMPTS.get(image_type, PROMPTS["general"])
            if context:
                prompt += f"\n\nAdditional context about this image:\n{context}"
            
            # Build image content
            if image_path:
                # Local file - encode to base64
                with open(image_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')
                
                ext = Path(image_path).suffix.lower()
                media_types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp'}
                media_type = media_types.get(ext, 'image/png')
                
                image_content = {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{image_data}", "detail": "high"}
                }
            else:
                # URL
                image_content = {
                    "type": "image_url",
                    "image_url": {"url": image_url, "detail": "high"}
                }
            
            # Call GPT-4o Vision
            response = client.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=[{
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}, image_content]
                }],
                max_tokens=2000,
                temperature=0.3
            )
            
            description = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else 0
            
            return {
                "success": True,
                "description": description,
                "image_type": image_type,
                "tokens_used": tokens_used,
                "generated_at": datetime.utcnow().isoformat() + 'Z'
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "image_type": image_type
            }
    
    def process_page_images(
        self,
        page_id: str,
        space_key: str,
        page_title: str,
        image_info: Dict[str, Dict],  # From V2ImageManager
        content_blocks: List[Dict]
    ) -> Dict[str, Dict]:
        """
        Process images with description caching.
        
        Args:
            page_id: Confluence page ID
            space_key: Confluence space key
            page_title: Page title
            image_info: Dict from V2ImageManager with blob_url and image_hash
            content_blocks: Content blocks to get context
        
        Returns:
            Dict[filename] -> {description, image_type, from_cache, ...}
        """
        print(f"\n   📝 Generating descriptions for: {page_title}")
        
        descriptions = {}
        
        for filename, info in image_info.items():
            image_hash = info.get('image_hash', '')
            if not image_hash:
                continue
            
            print(f"\n      🖼️ {filename[:40]}...")
            
            # Check cache first
            cached = self.get_cached_description(space_key, page_id, page_title, image_hash)
            
            if cached and cached.get('description'):
                print(f"         ♻️ CACHED (generated {cached.get('generated_at', 'unknown')[:10]})")
                self.stats['from_cache'] += 1
                self.stats['cost_saved'] += self.COST_PER_IMAGE
                
                descriptions[filename] = {
                    'description': cached['description'],
                    'image_type': cached.get('image_type', 'general'),
                    'from_cache': True,
                    'image_hash': image_hash
                }
                continue
            
            # Need to generate new description
            print(f"         🤖 Calling GPT-4o Vision...")
            
            # Get context from nearby content blocks
            context = self._get_image_context(filename, content_blocks)
            
            # Generate description
            local_path = info.get('local_path')
            blob_url = info.get('blob_url')
            
            result = self.generate_description(
                image_path=local_path,
                image_url=blob_url if not local_path else None,
                context=context
            )
            
            if result['success']:
                self.stats['generated'] += 1
                self.stats['tokens_used'] += result.get('tokens_used', 0)
                
                # Cache the description
                cache_data = {
                    'description': result['description'],
                    'image_type': result['image_type'],
                    'tokens_used': result.get('tokens_used', 0),
                    'generated_at': result['generated_at'],
                    'image_hash': image_hash,
                    'filename': filename
                }
                
                self.storage.save_description_cache(
                    space_key, page_id, page_title, image_hash, cache_data
                )
                
                print(f"         ✅ Generated & cached ({result.get('tokens_used', 0)} tokens)")
                
                descriptions[filename] = {
                    'description': result['description'],
                    'image_type': result['image_type'],
                    'from_cache': False,
                    'image_hash': image_hash,
                    'tokens_used': result.get('tokens_used', 0)
                }
            else:
                print(f"         ❌ Failed: {result.get('error', 'Unknown')}")
                self.stats['failed'] += 1
        
        # Print stats
        print(f"\n   📊 Description Stats:")
        print(f"      • From cache: {self.stats['from_cache']} (saved ~${self.stats['cost_saved']:.2f})")
        print(f"      • Generated: {self.stats['generated']} ({self.stats['tokens_used']:,} tokens)")
        print(f"      • Failed: {self.stats['failed']}")
        
        return descriptions
    
    def _get_image_context(self, filename: str, content_blocks: List[Dict]) -> str:
        """Get context from nearby content blocks for better description"""
        context_parts = []
        
        # Find the image block
        image_index = None
        for block in content_blocks:
            if block.get('type') == 'image' and block.get('filename') == filename:
                image_index = block.get('index', 0)
                if block.get('alt_text'):
                    context_parts.append(f"Alt text: {block['alt_text']}")
                break
        
        if image_index is None:
            return ""
        
        # Get nearby headings and text
        for block in content_blocks:
            idx = block.get('index', 0)
            if idx < image_index and idx >= image_index - 2:
                if block['type'] == 'heading':
                    context_parts.append(f"Section: {block['content']}")
                elif block['type'] == 'text':
                    context_parts.append(block['content'][:150])
        
        return " | ".join(context_parts)


def get_v2_description_generator(storage_manager: V2StorageManager = None) -> V2DescriptionGenerator:
    """Factory function"""
    return V2DescriptionGenerator(storage_manager)


# Test
if __name__ == "__main__":
    print("=" * 70)
    print("V2 DESCRIPTION GENERATOR TEST")
    print("=" * 70)
    
    generator = get_v2_description_generator()
    
    # Test type detection
    test_files = [
        "ProPM_flow_diagram.png",
        "RACI_matrix.png",
        "screenshot_email.jpg",
        "org_chart.png",
        "random_image.png"
    ]
    
    print("\nImage type detection:")
    for f in test_files:
        detected = generator.detect_image_type(f)
        print(f"  • {f} → {detected}")
    
    print("\n✅ V2 Description Generator initialized successfully")
