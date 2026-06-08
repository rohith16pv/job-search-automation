# Job Search Automation — n8n Workflow Engine

**Fully standalone** n8n-based job search automation. Zero dependencies on external systems.

Scan job portals → Evaluate fit → Tweak resume → Email you with briefing → You apply manually.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              n8n Automation Engine (Docker)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [Weekly Cron: Friday 9am]                                      │
│         ↓                                                       │
│  [1. Job Scanner]  (local config → mock jobs or real APIs)     │
│         ↓                                                       │
│  [2. Dedup Check]  (against local scan_history.jsonl)          │
│         ↓                                                       │
│  [3. Filter]       (by role, domain, location from profile)    │
│         ↓                                                       │
│  [4. Evaluate]     (Node.js script: keyword matching + score)   │
│         ↓                                                       │
│  [5. Resume Brief] (Google Docs: suggested reordering)         │
│         ↓                                                       │
│  [6. Draft Email]  (Gmail: send resume brief + job link)       │
│         ↓                                                       │
│  [7. Tracker]      (local applications.md)                     │
│         ↓                                                       │
│  [User Review]     ← Email with checklist, you decide          │
│                                                                 │
│ All Data Local:                                                │
│ - config/profile.yml (your profile)                            │
│ - config/cv.md (your resume)                                   │
│ - config/portals.yml (job sources)                             │
│ - data/scan_history.jsonl (dedup log)                          │
│ - data/applications.md (tracker)                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install Docker & Docker Compose
```bash
# macOS with Homebrew
brew install docker docker-compose
# Or use Docker Desktop: https://www.docker.com/products/docker-desktop

# Start Docker daemon (or open Docker Desktop app)
```

### 2. Clone & Setup
```bash
cd /Users/rohith/Downloads/Github/job-search-automation

# Create workflow directory
mkdir -p workflows scripts data

# Copy this repo's files
# (Already done by initialization)
```

### 3. Start n8n + Postgres
```bash
docker-compose up -d

# Wait for health check (~15s)
docker-compose ps

# View logs
docker-compose logs -f n8n
```

### 4. Access n8n UI
```
http://localhost:5678/
```

First run: set admin email + password.

### 5. Create Workflows
Import or build workflows in n8n UI (see Workflows section below).

### 6. Set Environment Variables
In n8n UI → Settings → Environment Variables:
```
CAREER_OPS_PATH=/workspace/career-ops
GMAIL_EMAIL=pv.rohith96@gmail.com
GOOGLE_DOCS_FOLDER_ID=<your-Google-Drive-folder-id>
WEBHOOK_BASE_URL=http://localhost:5678
```

## Workflows

### Workflow 1: `weekly-job-scan-and-email` (Core)
**Trigger:** Every Friday 9am PT

**Steps:**
1. **Trigger** (Cron): Friday 9am
2. **Run Career-Ops Scanner** (Webhook → Node.js script):
   - Call `/scripts/scan-wrapper.mjs`
   - Input: config from career-ops/portals.yml
   - Output: JSON array of new jobs
3. **Deduplication** (JavaScript node):
   - Read career-ops/data/scan-history.tsv
   - Filter out jobs already in history
   - Output: deduplicated jobs
4. **Relevance Filter** (JavaScript node):
   - Check job title (must match target roles from profile.yml)
   - Check domain keywords (payments, fintech, etc.)
   - Check location (against profile.yml allowed geographies)
   - Output: filtered jobs (top 5 ranked by score)
5. **Get CV Content** (Read File node):
   - Read career-ops/cv.md
   - Extract bullets by section
6. **Assessment Loop** (For Each):
   - For each job:
     a. **Call Evaluator** (Webhook → Node.js):
        - Call `/scripts/evaluate-job.mjs` with JD + CV
        - Input: job URL, JD text
        - Output: score (A-F), gaps, comp, legitimacy
     b. **Extract Keywords** (JavaScript):
        - Parse JD for skills/domain keywords
        - Match against CV sections
        - Suggest reordering
     c. **Create Google Doc** (Google Drive API):
        - Template: Resume Briefing Doc
        - Fill: job title, company, assessment, CV gaps, suggested reorder
        - Output: shareable link
     d. **Generate Email Draft** (JavaScript):
        - Use assessment blocks + doc link
        - Personalize with company name, role, gaps
        - Output: email HTML + plain text
7. **Send Email** (Gmail node):
   - To: pv.rohith96@gmail.com
   - Subject: "Job Brief: [Company] — [Role] ([Score]/5)"
   - Body: email draft from step 6d
   - Attach: PDF of CV (optional)
8. **Update Tracker** (Write File node):
   - Write TSV to batch/tracker-additions/{num}-{company}.tsv
   - Format: num | date | company | role | status | score | pdf | report | notes
9. **Send Digest Summary** (Gmail node):
   - Summary email: X jobs scanned, Y relevant, Z applied, Z skipped
   - Include table with links to all emails + tracker entries

---

### Workflow 2: `manual-job-brief` (On-Demand)
**Trigger:** Webhook (you paste a URL in n8n UI)

**Steps:**
1. **Job URL Input** (Webhook trigger with UI form)
2. **Fetch Job Content** (HTTP Request):
   - GET job URL
   - Parse HTML to extract JD text
   - Handle ATS-specific HTML (Greenhouse, Ashby, Lever, Workday)
3. **Liveness Check** (Playwright node):
   - Navigate to URL
   - Check: Apply button visible, JD content present, posting date recent
   - Output: is_live (bool), screenshot
4. **Steps 6-8 from Workflow 1** (Evaluate, create doc, email draft)
5. **Await User Approval** (Wait node):
   - Wait for user to click "Approve & Send" link in email
   - Or "Edit & Reorder" to tweak resume section order first
6. **If "Reorder":**
   - Show resume section reordering UI (JavaScript)
   - User selects: keep original, or use suggested reorder
   - Re-generate Google Doc with approved reorder
7. **Send Final Email** (Gmail):
   - With final tweaked resume link + job link

---

### Workflow 3: `auto-apply-batch` (Phase 3 — Scheduled)
**Trigger:** Daily 9am, OR on-demand via webhook

**Steps:**
1. **Get Pending Applications** (Read File):
   - Read applications.md (or separate pending-apps.json)
   - Filter: status = "Draft" and created_date > 7 days ago (not too fresh)
2. **Rate Limit Check** (JavaScript):
   - Check data/rate-limits.json
   - Max 5/day, max 3 from same company/week
   - Output: approved_applications, rate_limit_reason
3. **Liveness Check Loop** (For Each):
   - For each approved app:
     - Playwright: Navigate to job URL
     - Verify Apply button exists + job is still open
     - Output: is_live (bool)
4. **Form Auto-Fill** (Playwright node):
   - For live jobs:
     - Navigate to apply form
     - Auto-fill: name, email, experience level, resume link
     - Screenshot filled form
     - **PAUSE here** — user must manually click Submit in the form
     - (This respects the "no auto-submit" ethical boundary)
5. **Update Status** (File Write):
   - Mark as "Applied" + timestamp in applications.md
   - Log to data/apply-log.tsv

---

### Workflow 4: `daily-status-digest` (Information Only)
**Trigger:** Daily 5pm PT

**Steps:**
1. **Get Yesterday's Activity** (Read Files):
   - Read applications.md + apply-log.tsv
   - Filter: updated in last 24h
2. **Aggregate Stats** (JavaScript):
   - Count: interviews scheduled, rejections, new applications, no-response flagged
3. **Format Digest** (JavaScript):
   - HTML table: [Company | Role | Status | Last Activity | Days Since]
4. **Send Email** (Gmail):
   - To: user
   - Subject: "Daily Job Search Digest — [Date]"
   - Body: table + action items

---

## Fully Standalone

All data lives locally. No dependencies on external systems:

| File | Purpose | Format |
|---|---|---|
| `config/profile.yml` | Your profile (name, email, target roles, location, keywords) | YAML |
| `config/cv.md` | Your resume (sections: Experience, Projects, Education, Skills) | Markdown |
| `config/portals.yml` | ATS portals to scan (Greenhouse, Ashby, Lever, LinkedIn, etc.) | YAML |
| `data/scan_history.jsonl` | Dedup log (which jobs we've already seen) | JSONL |
| `data/applications.md` | Application tracker (company, role, status, score, result) | Markdown |

**No external dependencies:**
- ✅ Runs locally in Docker
- ✅ All data stored locally
- ✅ Can work offline
- ✅ Nothing synced to external services (unless you enable Google Docs/Gmail)

---

## Environment Setup

### Google Docs API (for resume tweaking)

1. Create Google Cloud project: https://console.cloud.google.com
2. Enable Google Docs API + Google Drive API
3. Create Service Account key (JSON)
4. Share a Google Drive folder with the service account email
5. In n8n: add Google Docs credentials using the JSON key
6. Set env var: `GOOGLE_DOCS_FOLDER_ID=<folder-id-from-url>`

### Gmail API (for emailing)

1. In Google Cloud project: Enable Gmail API
2. Create OAuth 2.0 credentials (Desktop app)
3. Download credentials.json
4. In n8n: authenticate with Gmail credentials
5. In n8n: set env var `GMAIL_EMAIL=pv.rohith96@gmail.com`

### LinkedIn (Optional)

**Option A (Recommended):** Skip LinkedIn, rely on ATS portals (scan.mjs handles 80% of jobs)

**Option B (Paid):** Use Apify LinkedIn Jobs Actor ($15-20/month)
- In n8n: add Apify credentials
- Add HTTP node to call Apify API

**Option C (DIY):** LinkedIn scraping is against ToS and gets blocked. Not recommended.

---

## Scripts (Node.js Helpers)

All scripts in `/scripts` are called by n8n via HTTP webhooks or exec nodes.

### `/scripts/scan-wrapper.mjs`
Wrapper around career-ops scan.mjs. Returns new jobs as JSON.

**Input:**
```json
{
  "portals_path": "/workspace/career-ops/portals.yml"
}
```

**Output:**
```json
{
  "jobs": [
    {
      "id": "unique-id",
      "company": "Company Name",
      "role": "Role Title",
      "url": "https://...",
      "posted_date": "2026-06-08",
      "source": "greenhouse|ashby|lever|linkedin"
    }
  ],
  "count": 15,
  "timestamp": "2026-06-08T15:30:00Z"
}
```

### `/scripts/evaluate-job.mjs`
Minimal evaluator (calls career-ops evaluation or simple scoring).

**Input:**
```json
{
  "job_url": "https://...",
  "job_title": "Senior PM",
  "company": "Company",
  "jd_text": "Full JD content...",
  "cv_path": "/workspace/career-ops/cv.md"
}
```

**Output:**
```json
{
  "score": 4.2,
  "score_letter": "B",
  "gaps": ["No experience with FedNow"],
  "comp_estimate": "$250k-300k",
  "legitimacy_tier": "High",
  "suggested_sections": ["Projects", "Experience"],
  "keywords_matched": ["payments", "fintech", "settlement"]
}
```

### `/scripts/dedup-jobs.mjs`
Check job against career-ops scan-history.tsv.

**Input:**
```json
{
  "company": "Company",
  "role": "Role",
  "posting_url": "https://...",
  "scan_history_path": "/workspace/career-ops/data/scan-history.tsv"
}
```

**Output:**
```json
{
  "is_duplicate": false,
  "last_seen": "2026-05-15",
  "days_since": 24
}
```

---

## Configuration Files

### `.env.local` (Create locally, never commit)
```
CAREER_OPS_PATH=/Users/rohith/Downloads/Github/career-ops
GMAIL_EMAIL=pv.rohith96@gmail.com
GOOGLE_DOCS_FOLDER_ID=<get-from-drive-url>
APIFY_API_KEY=<optional-linkedin-scraper>
SENDGRID_API_KEY=<optional-email-service>
```

### `n8n/credentials.json` (Auto-generated by n8n UI)
- Gmail credentials
- Google Docs credentials
- Apify API key (optional)

---

## Monitoring & Logs

### View Workflow Runs
n8n UI → Executions tab shows all workflow runs + logs.

### Troubleshoot
```bash
# View n8n logs
docker-compose logs -f n8n

# View Postgres logs
docker-compose logs -f postgres

# Shell into n8n container
docker exec -it job-search-automation-n8n-1 /bin/bash

# Check integrations
curl http://localhost:5678/api/v1/health
```

### Backup Workflows
```bash
# Export workflow JSON from n8n UI → menu → Export Workflow
# Save to /workflows/{workflow-name}.json
# They're automatically synced to host via volume mount
```

---

## Testing Workflows (Phase 1)

### Test 1: Manual Job Brief
1. Visit n8n UI
2. Open "manual-job-brief" workflow
3. Click "Execute Workflow"
4. Paste a job URL in the input form
5. Watch execution logs
6. Receive email with resume brief

**Expected:** Email arrives in <2 min with Google Doc link + resume suggestions.

### Test 2: Weekly Scan (Manual Run)
1. n8n UI → "weekly-job-scan-and-email"
2. Click "Execute Workflow"
3. Watch it scan portals, evaluate top 5 jobs, send you a digest

**Expected:** 5 emails in your inbox in <5 min, with resume briefs + tracker entries created in batch/.

### Test 3: Merge with career-ops
1. After test 2, run:
   ```bash
   cd ../career-ops
   node merge-tracker.mjs
   ```
2. Check applications.md for new entries

**Expected:** New rows added to applications.md with scores, links, status = "Evaluated".

---

## FAQ

**Q: Does this modify career-ops?**
A: No. n8n only reads career-ops files. It writes to `batch/tracker-additions/` TSV files, which are merged manually via `merge-tracker.mjs` (existing career-ops script). career-ops remains source of truth.

**Q: Can I run this without Docker?**
A: Yes. Install n8n via npm: `npm install -g n8n`, then `n8n start`. You'll need to manually configure Postgres or use SQLite. Docker is simpler.

**Q: How do I schedule workflows?**
A: n8n has a built-in Cron trigger node. Set it to "Friday 9am PT" or "Daily 9am PT". n8n container must stay running 24/7 (use `docker-compose up -d`).

**Q: What if Google Docs API fails?**
A: n8n workflow falls back to markdown report (saved locally) and emails the markdown preview instead.

**Q: What if a job URL doesn't parse (Playwright fails)?**
A: Workflow logs the error, skips that job, continues with others. Summary email notes how many failed (if any).

**Q: How do I disable auto-apply (Workflow 3) for now?**
A: Don't deploy Workflow 3 yet. Workflows 1 + 2 are phase 1 (email + review). Workflow 3 is phase 3 (scheduled apply).

**Q: Can I use SendGrid instead of Gmail?**
A: Yes. Replace Gmail node with SendGrid HTTP node. Update email sending logic in JavaScript node.

**Q: How do I add more job sources (e.g., LinkedIn)?**
A: In Workflow 1, step 2: add another branch before deduplication. Call Apify Actor or custom LinkedIn scraper. Merge results with ATS jobs. Same downstream logic.

---

## Next Steps

1. **Start Docker:** `docker-compose up -d`
2. **Access n8n:** http://localhost:5678
3. **Create Admin Account:** First run prompt
4. **Test Workflow 1 (Manual Brief):** Paste a job URL, verify email
5. **Test Workflow 2 (Weekly Scan):** Execute manually, check results
6. **Merge with career-ops:** Run `merge-tracker.mjs`, verify tracker updated
7. **Deploy Cron:** Enable "weekly-job-scan-and-email" cron trigger for Friday 9am

**Estimated time to working automation: 30 min setup + 30 min testing = 1 hour.**

---

## Support

- **n8n Docs:** https://docs.n8n.io
- **n8n Community:** https://community.n8n.io
- **career-ops integration:** See `scripts/` folder for Node.js helpers
- **Troubleshooting:** Check docker-compose logs, n8n Executions tab, browser console

