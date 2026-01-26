"""
Pages Configuration
===================
Defines which Confluence pages to monitor for the digest pipeline.

This file controls:
- Which pages are actively monitored
- Page metadata (IDs, titles, space keys)
- Recursive crawling options (commented out by default)

To modify monitored pages:
1. Edit ACTIVE_PAGES list below, OR
2. Create a pages.json file in the config/ folder

Each page gets its own:
- data/pages/{space}/{page_id}/document.json
- Separate change detection hash
- Independent chunk indexing (old chunks deleted on update)
"""

import os
import json
from pathlib import Path

# =============================================================================
# SPACE CONFIGURATION
# =============================================================================
SPACE_KEY = "CIPPMOPF"
SPACE_URL = "https://eaton-corp.atlassian.net/wiki/spaces/CIPPMOPF"

# =============================================================================
# ACTIVE PAGES TO MONITOR
# =============================================================================
# These are the pages currently being monitored for changes.
# Each page will have its own document.json and separate index chunks.

ACTIVE_PAGES = [
    {
        "page_id": "164168599",
        "title": "ProPM Roles & Responsibilities",
        "space_key": "CIPPMOPF"
    },
    # Add more subpages here as needed:
    # {
    #     "page_id": "XXXXXXXXX",
    #     "title": "Subpage Title 1",
    #     "space_key": "CIPPMOPF"
    # },
    # {
    #     "page_id": "XXXXXXXXX",
    #     "title": "Subpage Title 2",
    #     "space_key": "CIPPMOPF"
    # },
    # {
    #     "page_id": "XXXXXXXXX",
    #     "title": "Subpage Title 3",
    #     "space_key": "CIPPMOPF"
    # },
]

# =============================================================================
# RECURSIVE CRAWLING (COMMENTED - FUTURE USE)
# =============================================================================
# Uncomment below to enable recursive crawling of parent page and all children
# This will automatically discover and monitor all subpages

# ENABLE_RECURSIVE_CRAWL = True
# PARENT_PAGE_CONFIG = {
#     "page_id": "304287253",  # "ARCHIVED - To be deleted" parent page
#     "title": "ARCHIVED - To be deleted",
#     "space_key": "CIPPMOPF",
#     "crawl_children": True,
#     "max_depth": 3  # How many levels deep to crawl
# }
#
# def get_child_pages(parent_page_id, depth=0, max_depth=3):
#     """
#     Recursively get all child pages of a parent page.
#     
#     Args:
#         parent_page_id: Confluence page ID
#         depth: Current recursion depth
#         max_depth: Maximum depth to crawl
#     
#     Returns:
#         List of page configs for all children
#     """
#     import requests
#     from requests.auth import HTTPBasicAuth
#     from dotenv import load_dotenv
#     
#     load_dotenv()
#     
#     if depth >= max_depth:
#         return []
#     
#     CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
#     AUTH = HTTPBasicAuth(
#         os.getenv("CONFLUENCE_EMAIL"),
#         os.getenv("CONFLUENCE_API_TOKEN")
#     )
#     
#     url = f"{CONFLUENCE_URL}/rest/api/content/{parent_page_id}/child/page"
#     response = requests.get(url, auth=AUTH, verify=False)
#     
#     if response.status_code != 200:
#         return []
#     
#     children = response.json().get('results', [])
#     pages = []
#     
#     for child in children:
#         page_config = {
#             "page_id": child['id'],
#             "title": child['title'],
#             "space_key": SPACE_KEY
#         }
#         pages.append(page_config)
#         
#         # Recursively get grandchildren
#         pages.extend(get_child_pages(child['id'], depth + 1, max_depth))
#     
#     return pages


# =============================================================================
# CONFIGURATION LOADER
# =============================================================================

def load_pages_config():
    """
    Load pages configuration.
    
    Priority:
    1. config/pages.json (if exists)
    2. ACTIVE_PAGES list (default)
    
    Returns:
        List of page configurations
    """
    # Check for external config file
    config_file = Path("config/pages.json")
    
    if config_file.exists():
        print(f"[CONFIG] Loading pages from {config_file}")
        with open(config_file, 'r') as f:
            config = json.load(f)
            return config.get('pages', [])
    
    # Use default ACTIVE_PAGES
    print(f"[CONFIG] Using default ACTIVE_PAGES ({len(ACTIVE_PAGES)} pages)")
    return ACTIVE_PAGES


def get_pages_to_monitor():
    """
    Get list of all pages to monitor.
    
    Returns:
        List of dicts with page_id, title, space_key
    """
    # # UNCOMMENT FOR RECURSIVE CRAWLING:
    # if ENABLE_RECURSIVE_CRAWL:
    #     print("[CONFIG] Recursive crawl enabled - discovering child pages...")
    #     parent = PARENT_PAGE_CONFIG
    #     pages = [{
    #         "page_id": parent["page_id"],
    #         "title": parent["title"],
    #         "space_key": parent["space_key"]
    #     }]
    #     pages.extend(get_child_pages(
    #         parent["page_id"], 
    #         max_depth=parent.get("max_depth", 3)
    #     ))
    #     return pages
    
    return load_pages_config()


def get_page_data_path(page_id, space_key):
    """
    Get the data path for a specific page.
    Each page has its own folder for document.json
    
    Args:
        page_id: Confluence page ID
        space_key: Space key
    
    Returns:
        Path to page data folder
    """
    return Path(f"data/pages/{space_key}/{page_id}")


def get_page_document_path(page_id, space_key):
    """
    Get path to document.json for a specific page.
    
    Args:
        page_id: Confluence page ID
        space_key: Space key
    
    Returns:
        Path to document.json
    """
    return get_page_data_path(page_id, space_key) / "document.json"


# =============================================================================
# CLI FOR TESTING
# =============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("PAGES CONFIGURATION")
    print("=" * 60)
    
    pages = get_pages_to_monitor()
    
    print(f"\nMonitoring {len(pages)} page(s):\n")
    
    for i, page in enumerate(pages, 1):
        print(f"  {i}. {page['title']}")
        print(f"     ID: {page['page_id']}")
        print(f"     Space: {page['space_key']}")
        print(f"     Data: {get_page_data_path(page['page_id'], page['space_key'])}")
        print()
    
    print("=" * 60)
