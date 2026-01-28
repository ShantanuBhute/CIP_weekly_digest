"""Debug the sectioning logic"""
import json
import sys
import os

from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
load_dotenv()

STORAGE_CONNECTION_STRING = os.environ.get('BLOB_STORAGE_CONNECTION_STRING')
blob_service = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING, connection_verify=False)
container = blob_service.get_container_client('confluence-rag')

# Get v9 of RACI
blob_client = container.get_blob_client('CIPPMOPF/RACI_17386855_v9.json')
content = json.loads(blob_client.download_blob().readall())
content_blocks = content['content_blocks']

def is_heading_like(block):
    if block['type'] == 'heading':
        return True
    if block['type'] == 'text':
        content = block.get('content', '')
        word_count = len(content.split())
        char_count = len(content)
        if char_count < 100 or word_count < 20:
            return True
    return False

# Simulate sectioning
sections = []
current_section = {'heading': None, 'blocks': [], 'start_index': 0}

for block in content_blocks:
    if is_heading_like(block):
        if current_section['blocks'] or current_section['heading']:
            sections.append(current_section)
        current_section = {
            'heading': block.get('content', '') if block['type'] in ['heading', 'text'] else None,
            'heading_level': block.get('level', 2) if block['type'] == 'heading' else 3,
            'blocks': [block],
            'start_index': block['index']
        }
    else:
        current_section['blocks'].append(block)

if current_section['blocks'] or current_section['heading']:
    sections.append(current_section)

print(f"Total sections: {len(sections)}")
for i, section in enumerate(sections):
    print(f"\nSection {i}: {section['heading'][:50] if section['heading'] else 'No heading'}...")
    print(f"  Blocks: {len(section['blocks'])}")
    for block in section['blocks']:
        block_type = block['type']
        if block_type == 'image':
            print(f"    - IMAGE: {block.get('filename')} (has desc: {bool(block.get('description'))})")
        elif block_type == 'text':
            print(f"    - TEXT: {block.get('content', '')[:40]}...")
        elif block_type == 'heading':
            print(f"    - HEADING: {block.get('content', '')[:40]}...")
        elif block_type == 'list':
            print(f"    - LIST: {len(block.get('items', []))} items")
        else:
            print(f"    - {block_type.upper()}")
