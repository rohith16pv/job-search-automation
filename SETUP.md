# Setup Guide — Job Search Automation

Complete setup steps to get n8n + automation running.

## Prerequisites

- macOS / Linux / Windows with Docker + Docker Compose
- Gmail account (for email integration)
- Google Cloud account (for Google Docs API) — optional but recommended
- career-ops repo at `/Users/rohith/Downloads/Github/career-ops`

## Step 1: Install Docker

**macOS:**
```bash
# Using Homebrew
brew install docker docker-compose

# Or use Docker Desktop (easier)
# Download from: https://www.docker.com/products/docker-desktop
```

**Linux:**
```bash
sudo apt-get install docker.io docker-compose
sudo usermod -aG docker $USER
```

**Verify:**
```bash
docker --version
docker-compose --version
```

## Step 2: Configure This Repo

```bash
cd /Users/rohith/Downloads/Github/job-search-automation

# Copy environment variables template
cp .env.example .env.local

# Edit .env.local with your details
vim .env.local
```

**Edit `./.env.local` (only Gmail/Google needed):**
```
GMAIL_EMAIL=pv.rohith96@gmail.com
GMAIL_APP_PASSWORD=<see step 3>
GOOGLE_DOCS_FOLDER_ID=<see step 4>
```

**Customize Your Profile (in `config/`):**
- `config/profile.yml` — your target roles, locations, keywords
- `config/cv.md` — your resume/CV
- `config/portals.yml` — which ATS sites to scan (Stripe, Square, etc.)

## Step 3: Set Up Gmail API

n8n will send emails on your behalf. You need an App Password (not your main Gmail password).

1. Go to: https://myaccount.google.com/apppasswords
2. Select: Mail, macOS (or your platform)
3. Google generates a 16-character password
4. Copy it to `.env.local`:
   ```
   GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
   ```

**In n8n UI later:**
- Create Gmail credential using your email + App Password
- Test the credential by sending a test email

## Step 4: Set Up Google Docs API (Optional but Recommended)

For auto-creating resume briefing Google Docs:

1. Create Google Cloud project:
   - Go to: https://console.cloud.google.com
   - Click "Create Project"
   - Name: "job-search-automation"

2. Enable APIs:
   - In project, go to "APIs & Services" → "Library"
   - Search: "Google Docs API" → Enable
   - Search: "Google Drive API" → Enable

3. Create Service Account:
   - Go to "Credentials" → "Create Credentials" → "Service Account"
   - Name: "job-automation-service"
   - Finish (skip optional steps)
   - Click the created service account
   - Go to "Keys" tab → "Create New Key" → JSON
   - Save to: `./credentials/google-service-account.json`

4. Create Google Drive Folder:
   - Go to Google Drive
   - Create folder: "Job Search Automation"
   - Right-click → Share
   - Copy folder ID from URL (between `/folders/` and end)
   - Add to `.env.local`: `GOOGLE_DOCS_FOLDER_ID=<id>`
   - Share folder with service account email (from JSON): `{account-id}@{project-id}.iam.gserviceaccount.com`

**In n8n UI later:**
- Create Google Docs credential using JSON key
- Test by creating a sample document

## Step 5: Start n8n

```bash
# Start Docker containers
docker-compose up -d

# Wait for health check (10-15s)
sleep 15

# Check status
docker-compose ps

# View logs
docker-compose logs -f n8n
```

## Step 6: Access n8n & Create Admin

1. Open browser: http://localhost:5678
2. First run prompt:
   - Email: your email
   - Password: choose a strong one
3. Click "Set Up n8n"

## Step 7: Add Credentials to n8n

In n8n UI → Settings → Credentials:

### Gmail Credential
1. Click "New" → Search "Gmail"
2. Select "Gmail" (Gmail node)
3. Authentication: OAuth2
4. Click "Connect" → authenticate with your Google account
5. Grant permissions

### Google Docs Credential (if using)
1. Click "New" → Search "Google"
2. Select "Google Docs"
3. Authentication: Service Account (JSON key)
4. Paste contents of `./credentials/google-service-account.json`
5. Click "Save"

### Test Credentials
- For Gmail: Send test email to yourself
- For Google Docs: Try creating a test document

## Step 8: Import or Create Workflows

### Option A: Import Pre-Built Workflows
(Once they're exported and added to this repo)

```bash
# Workflows will be in ./workflows/ folder
# In n8n UI: Click "Workflows" → "Import" → select JSON file
```

### Option B: Create Manually in n8n UI

See README.md for workflow specifications.

## Step 9: Test the Setup

### Test 1: Manual Job Evaluation
1. n8n UI → Workflows → "manual-job-brief" (create if doesn't exist)
2. Click "Execute"
3. Paste a real job URL or use test data
4. Check email for resume brief

### Test 2: Run Scanner
1. In n8n UI, create a simple workflow:
   - Trigger: Manual
   - Node: "Execute Command" → `node /workspace/scripts/scan-wrapper.mjs`
   - Output: JSON array of new jobs
2. Click "Execute"
3. Check logs for results

### Test 3: Check Local Tracker
```bash
# View your applications
cat data/applications.md

# View your profile
cat config/profile.yml

# View scan history
cat data/scan_history.jsonl
```

## Step 10: Schedule Recurring Workflows

In n8n UI:

1. Open "weekly-job-scan-and-email" workflow
2. Click on Trigger node
3. Set Cron: 
   - Type: "Cron"
   - Time: "0 9 * * 3" (Wednesday 9am)
   - Timezone: "America/Los_Angeles"
4. Click "Save"

Repeat for:
- "digest-email": Friday 5pm
- "auto-apply-batch" (Phase 3): Daily 9am

## Troubleshooting

### "Cannot connect to career-ops"
- Check: `ls -la /Users/rohith/Downloads/Github/career-ops`
- Check Docker volumes: `docker-compose exec n8n ls -la /workspace/career-ops`

### "Gmail authentication failed"
- Regenerate App Password (may have expired)
- Check: Settings → Gmail credential

### "Google Docs API returns 403"
- Check: Service account has access to folder
- Verify folder is shared with service account email

### "n8n won't start"
```bash
docker-compose down -v  # Remove volumes
docker-compose up -d    # Fresh start
```

### "Workflows not running on schedule"
- Check: Cron syntax in trigger node
- Verify: n8n container is running 24/7
- Check: System timezone matches n8n timezone

## Next Steps

1. **Day 1:** Get n8n running, test credentials
2. **Day 2:** Test manual job brief workflow
3. **Day 3:** Set up Google Docs integration (optional)
4. **Day 4-5:** Deploy scheduled workflows
5. **Week 2:** Monitor, tweak relevance filters, iterate

## Support Resources

- **n8n Docs:** https://docs.n8n.io
- **n8n Community:** https://community.n8n.io
- **This Project:** See README.md
- **career-ops:** See ../career-ops/CLAUDE.md

