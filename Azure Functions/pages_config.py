"""
Pages Configuration for Azure Functions
Reads from environment variables instead of local JSON
"""

import os

SPACE_KEY = os.getenv("SPACE_KEY", "CIPPMOPF")


def get_pages_to_monitor():
    """
    Get list of pages to monitor from environment variables.
    
    Environment variable PAGE_IDS should be comma-separated page IDs.
    Example: PAGE_IDS=164168599,166041865,17386855,439124075
    """
    page_ids_str = os.getenv("PAGE_IDS", "")
    
    if not page_ids_str:
        return []
    
    pages = []
    for pid in page_ids_str.split(","):
        pid = pid.strip()
        if pid:
            pages.append({
                "page_id": pid,
                "title": f"Page {pid}",
                "space_key": SPACE_KEY
            })
    
    return pages
