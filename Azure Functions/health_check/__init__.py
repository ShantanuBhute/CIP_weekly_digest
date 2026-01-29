"""
Health Check - Simple HTTP Function to verify deployment
"""

import os
import azure.functions as func
import json
from datetime import datetime


def main(req: func.HttpRequest) -> func.HttpResponse:
    """Simple health check endpoint with environment debug info"""
    
    # Common Azure environment variables to check
    env_vars = [
        "AZURE_FUNCTIONS_ENVIRONMENT",
        "WEBSITE_INSTANCE_ID",
        "WEBSITE_SITE_NAME",
        "FUNCTIONS_WORKER_RUNTIME",
        "WEBSITE_HOSTNAME",
        "AzureWebJobsScriptRoot",
        "HOME",
        "FUNCTIONS_EXTENSION_VERSION"
    ]
    
    env_status = {}
    for var in env_vars:
        val = os.getenv(var)
        if val:
            env_status[var] = val[:50] + "..." if len(val) > 50 else val
        else:
            env_status[var] = "not_set"
    
    # Determine if we're in Azure
    is_azure = any([
        os.getenv("AZURE_FUNCTIONS_ENVIRONMENT"),
        os.getenv("WEBSITE_INSTANCE_ID"),
        os.getenv("WEBSITE_SITE_NAME"),
        os.getenv("FUNCTIONS_WORKER_RUNTIME")
    ])
    
    if is_azure:
        data_folder = "/tmp/data"
    else:
        data_folder = "data"
    
    return func.HttpResponse(
        json.dumps({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Function app is running!",
            "is_azure_detected": is_azure,
            "data_folder_would_be": data_folder,
            "env_vars": env_status
        }, indent=2),
        status_code=200,
        mimetype="application/json"
    )
