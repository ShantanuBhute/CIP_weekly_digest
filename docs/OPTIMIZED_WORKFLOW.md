# Single Page Monitoring System - Optimized Workflow

## Overview

Monitors **ONE specific Confluence page** with smart change detection to save compute costs.

**Target Page:** ProPM Roles & Responsibilities  
**Page ID:** 164168599  
**URL:** https://eaton-corp.atlassian.net/wiki/spaces/CIPPMOPF/pages/164168599

## Smart Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: CHANGE DETECTION (Optimized)                      │
│  - Extract raw text from Confluence                         │
│  - Calculate SHA256 hash                                    │
│  - Compare with previous version stored in blob             │
│  - If IDENTICAL → Skip processing, use existing data       │
│  - If DIFFERENT → Increment version, trigger reprocessing  │
└─────────────────┬───────────────────────────────────────────┘
                  │
      ┌───────────┴──────────┐
      │                      │
   UNCHANGED              CHANGED
      │                      │
      │           ┌──────────▼──────────────────────────────┐
      │           │  STEP 2: FULL PIPELINE                  │
      │           │  - Extract content + images             │
      │           │  - Describe images with GPT-4o Vision   │
      │           │  - Upload to blob storage               │
      │           │  - Chunk and index in AI Search         │
      │           └──────────┬──────────────────────────────┘
      │                      │
      └──────────┬───────────┘
                 │
    ┌────────────▼─────────────────────────────────────────┐
    │  STEP 3: GENERATE EMAIL DIGEST                       │
    │  - Retrieve indexed content from AI Search           │
    │  - Generate AI summary using GPT-4o + RAG            │
    │  - Format beautiful HTML email                       │
    │  - Save to data/emails/                              │
    └──────────────────────────────────────────────────────┘
```

## Key Optimization: Text Comparison

### Why This Saves Compute

**Before (Naive Approach):**
- Always extract → describe → upload → index
- Cost: ~$0.50 per run (GPT-4o Vision + embeddings)
- Weekly: $26/year

**After (Smart Approach):**
- Extract raw text → compare hash → only reprocess if changed
- Cost if unchanged: $0.00 (just text comparison)
- Cost if changed: $0.50
- Weekly with 10% change rate: ~$2.60/year (**90% savings!**)

### How Version Tracking Works

**State stored in `confluence-state` container:**

```json
{
  "page_id": "164168599",
  "version_number": 11,
  "content_hash": "a3f5b2c8...",
  "raw_text": "TITLE: ProPM Roles...",
  "extracted_at": "2026-01-26T10:00:00",
  "confluence_version": 11
}
```

**On each run:**
1. Extract current raw text
2. Calculate SHA256 hash
3. Compare with stored hash
4. If match → version stays same, skip processing
5. If different → increment version, run full pipeline

**Version history preserved:**
- Current: `page_164168599_raw_version.json`
- History: `page_164168599_history/v11_20260126_100000.json`

## Files Created

### New Optimized Scripts

1. **single_page_monitor.py**
   - Smart change detection using text hashing
   - Stores raw text versions in blob
   - Only increments version on actual changes

2. **run_single_page_pipeline.py**
   - Orchestrates complete workflow
   - Calls monitor → pipeline → email generator
   - Skips reprocessing if content unchanged

3. **email_digest_generator.py**
   - Retrieves indexed content from AI Search
   - Generates AI summary using GPT-4o + RAG
   - Creates beautiful HTML email digest
   - Adapts message based on whether changes detected

### Workflow Diagram

```python
# run_single_page_pipeline.py

def run_single_page_workflow():
    # Phase 1: Detect changes
    change_result = detect_changes_optimized(PAGE_ID)
    
    if change_result['needs_reprocessing']:
        # Phase 2: Full pipeline (only if changed)
        run_full_pipeline(PAGE_ID, version)
    
    # Phase 3: Generate email (always)
    generate_page_summary_email(PAGE_ID, ...)
```

## Usage

### Manual Run

```bash
# Complete workflow
python run_single_page_pipeline.py

# Output:
# - Checks for changes
# - Reprocesses only if needed
# - Generates email digest
# - Saves to data/emails/digest_164168599_v11_*.html
```

### Expected Output

**Scenario 1: No Changes**
```
===============================================================================
CHANGE DETECTION: Page 164168599
===============================================================================
✅ NO CHANGES DETECTED
   Content hash matches: a3f5b2c8...
   Keeping version: v11

✅ NO CHANGES - Using existing indexed content

EMAIL DIGEST GENERATION
✅ Retrieved 15 chunks
✅ Summary generated
📧 HTML: data/emails/digest_164168599_v11_20260126_100000.html
```

**Scenario 2: Changes Detected**
```
===============================================================================
CHANGE DETECTION: Page 164168599
===============================================================================
✏️ CHANGES DETECTED
   Previous hash: a3f5b2c8...
   Current hash:  b4e6c3d9...
   Content modified: 5 lines added, 2 lines removed
   Incrementing version: v11 → v12

📢 CHANGES DETECTED - Running full pipeline...

FULL PIPELINE EXECUTION
├─ STEP 1: Extracting content... ✅ 15 blocks
├─ STEP 2: Describing images... ✅ 4 images
├─ STEP 3: Uploading to blob... ✅
└─ STEP 4: Indexing in AI Search... ✅ 15 chunks

EMAIL DIGEST GENERATION
✅ Retrieved 15 chunks
✅ Summary generated
📧 HTML: data/emails/digest_164168599_v12_20260126_100000.html
```

## Email Output Example

The generated HTML email includes:

### Header Section
- Page title with icon
- Generated timestamp
- Version number
- Direct link to Confluence page

### Change Badge (if applicable)
```
📝 Recent Changes: Content modified: 5 lines added, 2 lines removed
```

### Executive Summary
AI-generated summary covering:
- **Overview** - What the page is about
- **Key Information** - Important points documented
- **Recent Updates** - What changed (if changes detected)
- **Action Items** - Actionable insights

### Content Preview
- First 10 content blocks (headings, images)
- Shows structure of the page
- Links back to full page

### Professional Styling
- Clean, modern design
- Mobile-responsive
- Corporate blue color scheme
- Clear call-to-action button

## Integration with Logic Apps

### Simplified Workflow

```json
{
  "triggers": {
    "Recurrence": {
      "frequency": "Week",
      "interval": 1,
      "schedule": {
        "hours": ["9"],
        "weekDays": ["Friday"]
      }
    }
  },
  "actions": {
    "Run_Pipeline": {
      "type": "Http",
      "inputs": {
        "method": "GET",
        "uri": "https://your-function.azurewebsites.net/api/single-page-workflow"
      }
    },
    "Parse_Result": {
      "type": "ParseJson",
      "inputs": {
        "content": "@body('Run_Pipeline')"
      }
    },
    "Send_Email": {
      "type": "ApiConnection",
      "inputs": {
        "host": {
          "connection": {
            "name": "@parameters('$connections')['office365']"
          }
        },
        "method": "post",
        "path": "/v2/Mail",
        "body": {
          "To": "cip-team@eaton.com",
          "Subject": "ProPM Roles & Responsibilities - Weekly Update",
          "Body": "@body('Parse_Result')?['html_content']",
          "IsHtml": true
        }
      }
    }
  }
}
```

## Cost Analysis

### Per-Run Costs (when changes detected)

| Component | Cost |
|-----------|------|
| Confluence API calls | $0.00 (free) |
| GPT-4o Vision (4 images × 200 tokens) | ~$0.02 |
| GPT-4o Summary (2000 tokens) | ~$0.01 |
| Embeddings (15 chunks × 1536 dims) | ~$0.0001 |
| Blob Storage | ~$0.00 |
| AI Search indexing | ~$0.00 (pay-per-use) |
| **Total per changed run** | **~$0.03** |

### Per-Run Costs (no changes)

| Component | Cost |
|-----------|------|
| Text extraction & comparison | $0.00 |
| Email generation (using cached index) | ~$0.01 |
| **Total per unchanged run** | **~$0.01** |

### Annual Estimate (52 weeks)

Assuming 5 changes per year (10% change rate):
- Changed runs: 5 × $0.03 = $0.15
- Unchanged runs: 47 × $0.01 = $0.47
- **Total: ~$0.62/year** 🎉

Compare to naive approach: $26/year (42x more expensive!)

## Testing

### Test Change Detection

```bash
# First run - should create v1
python single_page_monitor.py

# Second run immediately - should detect no changes
python single_page_monitor.py

# Manually edit page in Confluence, then run
python single_page_monitor.py  # Should detect changes, create v2
```

### Test Email Generation

```bash
# Generate email from existing indexed content
python email_digest_generator.py

# View generated HTML in browser
start data/emails/digest_164168599_v11_*.html
```

### Test Complete Workflow

```bash
# Full end-to-end test
python run_single_page_pipeline.py
```

## Scaling Strategy

When ready to monitor multiple pages:

1. **Modify `single_page_monitor.py`** to accept page_id parameter
2. **Create loop in Logic Apps** to iterate over page IDs
3. **Batch email generation** - combine multiple pages into one digest
4. **Use page-specific state** - each page has own version tracking

Example multi-page workflow:
```python
pages = [
    "164168599",  # ProPM Roles
    "164168600",  # Another page
    "164168601",  # Another page
]

changes_detected = []
for page_id in pages:
    result = detect_changes_optimized(page_id)
    if result['needs_reprocessing']:
        run_full_pipeline(page_id, result['version_number'])
        changes_detected.append(result)

# Generate combined digest
generate_multi_page_digest(changes_detected)
```

## Summary

✅ **Smart change detection** - 90% cost savings via text comparison  
✅ **Version tracking** - Incremental versioning only on changes  
✅ **Full pipeline** - Extract → Describe → Upload → Index  
✅ **AI-powered summaries** - GPT-4o with RAG context  
✅ **Beautiful emails** - Professional HTML formatting  
✅ **Logic Apps ready** - Single API endpoint for automation  
✅ **Cost optimized** - ~$0.62/year for weekly monitoring  

**Next Step:** Test locally with `python run_single_page_pipeline.py`
