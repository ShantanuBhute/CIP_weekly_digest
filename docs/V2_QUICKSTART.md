# V2 Optimized Pipeline - Quick Start

## 🎯 What's New in V2

### Cost Savings
| Optimization | Before (V1) | After (V2) | Savings |
|-------------|-------------|------------|---------|
| Image Downloads | ALL images every run | Only NEW/CHANGED | ~90% bandwidth |
| GPT-4o Vision | ALL images every run | Cached by hash | ~90% API cost |
| Blob Uploads | Always upload | Skip if unchanged | ~80% transactions |

### Estimated Monthly Savings (100 pages, daily runs)
- **GPT-4o Vision**: $1,350/month saved (from $1,500 to ~$150)
- **Bandwidth**: ~900MB saved per run
- **Storage transactions**: ~8,000 fewer writes/month

---

## 📁 New Folder Structure

```
cipdigest2 (V2 Storage Account)
│
├── confluence-content/
│   └── CIPPMOPF/
│       └── {PageTitle}_{PageID}/
│           ├── metadata.json          ← Version history
│           ├── versions/
│           │   ├── v1.json            ← Full document
│           │   ├── v2.json
│           │   └── ...
│           ├── images/                ← Deduplicated by hash
│           │   ├── a3f2b8c1_flowchart.png
│           │   └── d4e5f6a7_diagram.png
│           └── descriptions/          ← Cached GPT-4o results
│               ├── a3f2b8c1.json
│               └── d4e5f6a7.json
│
├── confluence-state/                  ← Change detection (unchanged)
│   └── page_{id}_raw_version.json
│
└── confluence-emails/                 ← Email digests (unchanged)
```

---

## 🚀 Quick Start

### 1. Setup V2 Environment

```powershell
# Navigate to project
cd c:\CODES\CIP_Weekly_digest

# Copy V2 environment (uses cipdigest2 storage)
copy "Azure Functions\.env.v2" .env

# Verify storage account
findstr "AZURE_STORAGE_ACCOUNT_NAME\|AccountName" .env
# Should show: cipdigest2
```

### 2. Run V2 Tests

```powershell
# Activate virtual environment
.\.venv\Scripts\activate

# Run test suite (no API costs)
python test_v2.py

# Run full pipeline test (costs ~$0.50 for GPT-4o)
python test_v2.py --full
```

### 3. Run V2 Pipeline

```powershell
# Process single page
python v2_pipeline.py --page 164168599

# Process all configured pages
python v2_pipeline.py

# Force reprocess (ignore cache)
python v2_pipeline.py --force
```

---

## 📋 V2 Modules

| Module | Purpose | Key Feature |
|--------|---------|-------------|
| `v2_storage_manager.py` | Blob operations | MD5 hash check before upload |
| `v2_image_manager.py` | Image downloads | Cache check before download |
| `v2_description_generator.py` | GPT-4o Vision | Description cache by image hash |
| `v2_pipeline.py` | Orchestration | Integrates all V2 modules |
| `test_v2.py` | Testing | Verify V2 setup |

---

## 🔄 Switching Between V1 and V2

### Use V2 (cipdigest2 - testing)
```powershell
copy "Azure Functions\.env.v2" .env
```

### Use V1 (cipdigest - production)
```powershell
copy "Azure Functions\.env" .env
# Or restore from backup:
copy "Azure Functions\.env.v1.backup" .env
```

---

## ⚠️ Important Notes

1. **V2 storage is separate** - cipdigest2 won't affect cipdigest (V1)
2. **First run downloads all images** - cache builds on first run
3. **GPT-4o costs** - First run for each image costs ~$0.05, then cached
4. **Test locally first** - Use `test_v2.py` before deploying to Azure Functions

---

## 🔧 Azure Functions Deployment

To deploy V2 to Azure Functions:

1. Copy V2 modules to Azure Functions folder
2. Update environment variables in Azure Portal
3. Deploy using `func azure functionapp publish`

```powershell
# Copy V2 modules
copy v2_*.py "Azure Functions\"

# Deploy
cd "Azure Functions"
func azure functionapp publish <your-function-app-name>
```

---

## 📊 Monitoring V2 Performance

After running V2 pipeline, check the summary:

```
V2 PIPELINE OPTIMIZATION SUMMARY
======================================================================

📄 Pages:
   • Processed: 4
   • With changes: 1

🖼️ Images:
   • Downloaded: 2
   • From cache: 38 (skipped download)

📝 Descriptions:
   • Generated (GPT-4o): 2
   • From cache: 38 (FREE)
   • Estimated cost saved: $1.90

📦 Uploads:
   • Performed: 3
   • Skipped (unchanged): 45
```
