CIP Weekly Knowledge Digest — Local‑First Implementation Plan (Confluence → Blob → Vector RAG → Weekly Email)
0) Purpose (what we’re building)
Build a system that:

Ingests Confluence pages into Azure Blob Storage as one JSON per page version
Chunks & indexes the page content into Azure AI Search with embeddings (vector RAG-ready)
Generates and sends:

Weekly digest (“topics covered”)
Change digest (“what’s new/changed since last run”)


Handles updates and later deletions, and can be manually triggered during testing.


1) Constraints & Current Status
Constraints

Local-first development only

Run everything using Azure Functions extension in VS Code
No Azure Portal development required right now


Secrets in local.settings.json (do not commit)
Schedules should run twice per week, not hourly
Email sending can be staged:

During local dev, email can be printed/logged or SendGrid; Logic App can be integrated later



Current status

Confluence API read access exists (basic operations working)
Test dataset:

Use an ARCHIVED “To be deleted” Confluence space/folder approved as non-sensitive




2) High-Level Architecture (Pipeline View)
Sources

Confluence pages (for now)

Storage

Azure Blob Storage: raw snapshots + artifacts + state

Index

Azure AI Search: chunk-level docs with embeddings + metadata filters

Compute

Azure Functions (Python) running locally in VS Code:

SyncConfluence (ingest + index)
WeeklyDigest (weekly topics)
ChangeDigest (delta changes)
RunNow (manual trigger for testing)



Email

Phase 1: dev print / SendGrid
Phase 2: Logic App HTTP trigger (or Graph API)


3) Pipelines (What gets built first)
Pipeline A — Ingest (Snapshot to Blob)
Goal
For each Confluence page:

Fetch metadata + body
Normalize to plain text
Save one JSON file per page version in Blob

Blob storage layout (recommended)
Use 3 containers (or one container with these prefixes):


confluence-pages

pages/<spaceKey>/<pageId>/v<version>/page.json



confluence-artifacts

artifacts/chunks/<pageId>/v<version>/chunks_manifest.json
artifacts/summaries/<weekly|delta>/<timestamp>.json
artifacts/outbound-mail/<timestamp>_<type>.json



confluence-state

state/pages_state.json



Snapshot JSON schema (minimum)
JSON{  "page_id": "12345",  "space_key": "CIP",  "title": "CIP Projects",  "version": 17,  "last_modified": "2026-01-18T10:03:11Z",  "url": "https://.../wiki/spaces/.../pages/12345",  "content_text": "plain text extracted from body.storage",  "content_hash": "sha1-of-content_text",  "attachments": []}Show more lines
Success criteria (Pipeline A)

Running SyncConfluence produces a set of page.json snapshots in Blob
Snapshot paths follow the convention above
You can re-run and verify snapshots are overwritten only for updated pages (later)


Pipeline B — Index (Chunk + Embed + Upsert to AI Search)
Goal
Convert snapshots into chunk records and index them into Azure AI Search for RAG.
Chunking (MVP)

HTML → text
Chunk by fixed size with overlap (simple, reliable)
Later upgrade: heading-aware chunking

Embeddings

Use Azure OpenAI embedding deployment (e.g., text-embedding-3-large or whatever exists in your AOAI resource)

Azure AI Search index schema (chunk-level)
Required fields:

id (key): pageId:version:chunkIndex
page_id (filterable)
page_version (filterable)
space_key (filterable)
title (searchable or retrievable)
last_modified (filterable/sortable)
url (retrievable)
is_deleted (filterable)
content (searchable)
content_vector (vector field)

Indexing behavior (important)

On update, index the new version’s chunks using new IDs
Later: decide whether to keep old versions (history) or soft-delete old chunks

Success criteria (Pipeline B)

AI Search index exists and is queryable
Chunk docs are inserted with correct metadata
Retrieval returns chunks from the archived test space


Pipeline C — Change Tracking (Update now, Delete later)
Goal
Detect changes so the system can produce a “what’s new” digest and avoid reprocessing unchanged pages.
State file stored in Blob
confluence-state/state/pages_state.json:
JSON{  "last_run": "2026-01-19T10:00:00Z",  "pages": {    "12345": { "version": 17, "hash": "....", "last_modified": "..." }  },  "recent_changes": []}Show more lines
Update detection logic (MVP)
For each page during sync:

Compute content_hash = sha1(content_text)
Compare (version, hash) vs state.pages[page_id]
If changed:

write new snapshot
chunk + embed + index
append entry to recent_changes



recent_changes entry schema (MVP):
JSON{  "page_id": "12345",  "title": "CIP Projects",  "version": 18,  "changed_at": "2026-01-19T11:12:00Z",  "space_key": "CIP",  "url": "..."}Show more lines
Delete handling (phase later)
At end of each sync:

Build seen_page_ids during the run
Compare to state.pages.keys()
Any missing is a delete candidate:

Soft-delete in AI Search: set is_deleted=true for all chunk docs for that page_id
Optionally move blobs under archive/ prefix



Success criteria (Pipeline C)

Editing a Confluence page via UI + running sync again results in:

New blob version snapshot saved
State updated
recent_changes populated




Pipeline D — Digest Emails (Weekly + Change)
Weekly digest (topics overview)
Goal: Summarize “topics covered” across selected space(s) or overall index.
MVP retrieval options:

Retrieve top N recent chunks from AI Search (filter is_deleted=false)
Summarize with AOAI chat model

Persist output:

Save artifacts/summaries/weekly/<timestamp>.json
Save outbound mail payload under artifacts/outbound-mail/…

Change digest (“what’s new”)
Goal: Email only what changed since last digest.
MVP approach:

Use recent_changes list from state
Output list of changed pages (later upgrade to diffs)

Later upgrade:

Load previous snapshot text and current snapshot text from blob
Generate “before vs after” summary (real delta)

Persist output:

Save artifacts/summaries/delta/<timestamp>.json
Save outbound mail payload JSON

Email sending strategy

Phase 1 (local dev): print email to logs OR SendGrid
Phase 2: call Logic App HTTP trigger (send Outlook mail), and still save payload to Blob


4) Triggers (Twice per week + Manual testing)
All times are UTC (important for Dublin DST changes).
Recommended schedules (UTC):

sync_confluence: Mon & Thu 08:00 UTC
weekly_digest: Mon 09:05 UTC (after sync)
change_digest: Thu 09:05 UTC (after sync)
run_now (HTTP trigger): manual kick during testing

Manual test pattern:

Edit a Confluence page in UI
Hit run_now endpoint
Verify recent_changes and digest output includes the update


5) Local-first implementation plan (execution order)
Step 1 — Snapshot pipeline (Blob)

List pages from archived test space
Fetch page body + metadata
Normalize HTML to plain text
Write page.json per page per version to Blob

Done when: You see page snapshots in Blob for multiple pages.
Step 2 — Chunk + Embed + Index

Chunk page text
Generate embeddings
Create AI Search index if missing
Upsert chunk docs

Done when: You can query AI Search and retrieve chunk docs.
Step 3 — Update detection

Implement pages_state.json
Compare hash/version to detect changes
Append to recent_changes

Done when: Editing a page triggers a state change and new snapshot.
Step 4 — Weekly + Change digest outputs

Weekly: summarize top N chunks
Delta: summarize recent_changes
Save both summaries to Blob
Send email (or print)

Done when: A modified page shows up in delta digest output.
Step 5 — Delete handling (later)

Build seen_id set
Soft delete missing pages in AI Search
Save delete records to blob


6) Testing plan (using archived “To be deleted” space)
Test 1: Baseline ingestion

Run sync → verify snapshots + index count

Test 2: Update capture

Edit a page in UI (add a heading + 2 lines)
Run run_now
Verify:

new blob version exists (v<newVersion>)
state updated + recent_changes contains the page
change digest mentions it



Test 3: Delete capture (later)

Delete/move a test page
Run sync
Verify is_deleted is set in index and page no longer appears in retrieval


7) VS Code Azure Functions Project Layout (recommended)
confluence-rag/
├─ host.json
├─ local.settings.json     # secrets (do not commit)
├─ requirements.txt
├─ shared/
│  ├─ confluence_client.py
│  ├─ storage_blobs.py
│  ├─ chunking.py
│  ├─ embeddings.py
│  ├─ search_index.py
│  ├─ change_tracker.py
│  ├─ summarizer.py
│  └─ mailer.py
├─ SyncConfluence/         # TimerTrigger
├─ WeeklyDigest/           # TimerTrigger
├─ ChangeDigest/           # TimerTrigger
└─ RunNow/                 # HttpTrigger


8) Config keys (local.settings.json placeholders)
(Links will be filled by the user; Copilot should scaffold keys.)

Confluence:

CONFLUENCE_BASE_URL
CONFLUENCE_EMAIL
CONFLUENCE_API_TOKEN
CONFLUENCE_SPACE_KEYS (archived test space first)
CONFLUENCE_CQL (optional)


Storage:

BLOB_CONN_STR
BLOB_CONTAINER_PAGES
BLOB_CONTAINER_ARTIFACTS
BLOB_CONTAINER_STATE


AI Search:

SEARCH_ENDPOINT
SEARCH_API_KEY
SEARCH_INDEX


Azure OpenAI:

AOAI_ENDPOINT
AOAI_API_KEY
AOAI_EMBED_DEPLOYMENT
AOAI_CHAT_DEPLOYMENT


Email (optional for now):

SENDGRID_API_KEY OR LOGICAPP_MAIL_URL




9) Open decisions (to answer as project matures)

Confluence deployment: Cloud vs Server/DC (affects endpoints/auth style)
Email sending: SendGrid now vs Logic App vs Graph API
Keep history or delete old versions from index?
For “delta digest”, do we implement true before/after diffs now or later?


10) Next immediate deliverable (what to do now)
Implement Step 1 (Snapshot pipeline) fully against the archived test space:

List pages → fetch bodies → normalize → write page.json blobs.

Then proceed to Step 2 (Index pipeline).