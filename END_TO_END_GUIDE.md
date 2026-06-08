# End-to-End Setup Guide — Job Search Automation

Complete step-by-step instructions from zero to fully working automation.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Phase 1: Local Setup](#phase-1-local-setup)
3. [Phase 2: Configuration](#phase-2-configuration)
4. [Phase 3: Docker & n8n](#phase-3-docker--n8n)
5. [Phase 4: Create Workflows](#phase-4-create-workflows)
6. [Phase 5: Testing](#phase-5-testing)
7. [Phase 6: Production](#phase-6-production)

---

## Prerequisites

Before you start, you need:

- ✅ macOS, Linux, or Windows with WSL2
- ✅ Docker + Docker Compose installed
- ✅ Git installed
- ✅ Gmail account (optional, for email)
- ✅ Google Cloud account (optional, for Google Docs)
- ✅ 1 hour of free time

**Install Docker:**
```bash
# macOS
brew install docker docker-compose

# Or use Docker Desktop
# https://www.docker.com/products/docker-desktop
```

**Verify:**
```bash
docker --version
docker-compose --version
git --version
```

---

## Phase 1: Local Setup

### Step 1: Clone the Repository

```bash
# Option A: Clone from GitHub
git clone https://github.com/rohith16pv/job-search-automation
cd job-search-automation

# Option B: Use existing local repo
cd /Users/rohith/Downloads/Github/job-search-automation
```

### Step 2: Verify Files Exist

```bash
# Check all required files are present
ls -la config/
ls -la scripts/
ls -la data/
cat docker-compose.yml
cat README.md
```

**Expected output:**
```
config/:
  ├── profile.yml
  ├── cv.md
  └── portals.yml

scripts/:
  ├── scan-wrapper.mjs
  ├── evaluate-job.mjs
  ├── resume-tweaker.mjs
  └── dedup-jobs.mjs

data/:
  └── applications.md
```

### Step 3: Create Environment File

```bash
# Copy template
cp .env.example .env.local

# Edit with your details
nano .env.local
# or
vim .env.local
```

**Minimal config** (only required for now):
```
GMAIL_EMAIL=pv.rohith96@gmail.com
```

---

## Phase 2: Configuration

### Step 4: Customize Your Profile

Edit `config/profile.yml`:

```bash
nano config/profile.yml
```

**Fill in:**
- `candidate.full_name` — Your name
- `candidate.email` — Your email
- `candidate.location` — Where you are
- `targeting.target_roles` — What roles you want (e.g., "Senior PM", "Staff PM")
- `targeting.locations` — Where you want to work (e.g., "San Francisco", "Remote")
- `targeting.domain_keywords` — What matters to you (e.g., "payments", "fintech")
- `compensation.target_base_min` — Salary minimum
- `compensation.target_base_max` — Salary maximum

**Example:**
```yaml
candidate:
  full_name: "Rohith Purimetla Vinay"
  email: "pv.rohith96@gmail.com"
  location: "San Francisco, CA"

targeting:
  target_roles:
    - "Senior Product Manager"
    - "Staff Product Manager"
  locations:
    - "San Francisco"
    - "Bay Area"
    - "Remote - US"
  domain_keywords:
    - "payments"
    - "fintech"
    - "settlement"
```

### Step 5: Customize Your Resume

Edit `config/cv.md`:

```bash
nano config/cv.md
```

**Sections to include:**
- Summary
- Experience (bullets with achievements)
- Projects
- Education
- Skills

**Format:**
```markdown
## Experience

### Company Name | Job Title
**Date Range**

- Bullet point 1 (quantified impact)
- Bullet point 2 (responsibility)
- Bullet point 3 (achievement)
```

### Step 6: Configure Job Sources

Edit `config/portals.yml`:

```bash
nano config/portals.yml
```

**Add/remove companies you want to scan:**
```yaml
portals:
  - name: "Stripe"
    careers_url: "https://jobs.stripe.com"
  - name: "Square"
    careers_url: "https://jobs.square.com"
  # Add more...
```

**Customize filters:**
```yaml
filters:
  title_keywords:
    positive:
      - "Senior Product Manager"
      - "Staff Product Manager"
    negative:
      - "Associate"
      - "Junior"
  
  domain_keywords:
    - "payments"
    - "fintech"
```

---

## Phase 3: Docker & n8n

### Step 7: Start Docker

```bash
# Verify Docker is running
docker ps

# If not running, start Docker Desktop (macOS) or daemon (Linux)
```

### Step 8: Start n8n + Postgres

```bash
cd /Users/rohith/Downloads/Github/job-search-automation

# Start the stack
docker-compose up -d

# Wait for health check
sleep 15

# Verify containers are running
docker-compose ps
```

**Expected output:**
```
NAME           STATUS
n8n            Up (healthy)
postgres       Up (healthy)
```

### Step 9: Access n8n UI

```bash
# Open in browser
open http://localhost:5678
```

**Or manually:** Go to `http://localhost:5678`

### Step 10: Create Admin Account

On first visit, n8n shows setup screen:

1. Enter your **email address**
2. Enter a **password** (strong, for local admin)
3. Click **Set Up n8n**
4. You're logged in ✅

---

## Phase 4: Create Workflows

### Step 11: Create First Workflow — Manual Job Brief

This workflow lets you paste a job URL and get a resume brief.

**In n8n UI:**

1. Click **Workflows** (left menu)
2. Click **New** (or blue + button)
3. Name: `manual-job-brief`
4. Add these nodes:

#### Node 1: Webhook Trigger
- Click **+** button
- Search "Webhook"
- Select "Webhook"
- Save
- Copy the webhook URL (you'll use it in step 12)

#### Node 2: HTTP Request (fetch job)
- Click **+** from Webhook
- Search "HTTP"
- Select "HTTP Request"
- Method: **GET**
- URL: (user will provide)
- Save

#### Node 3: Code (parse JD)
- Click **+** from HTTP Request
- Search "Code"
- Select "Code"
- Language: **JavaScript**
- Code:
```javascript
return items.map(item => ({
  jd_text: item.json.body,
  company: "Company",
  job_title: "Role Title"
}));
```
- Save

#### Node 4: HTTP Request (evaluate)
- Click **+** from Code
- Search "HTTP"
- Select "HTTP Request"
- Method: **POST**
- URL: `http://localhost:3002/evaluate`
- Body:
  - job_title: `{{ $node.Code.json.job_title }}`
  - company: `{{ $node.Code.json.company }}`
  - jd_text: `{{ $node.Code.json.jd_text }}`
  - config_path: `/workspace/config`
- Save

#### Node 5: Gmail (send email)
- Click **+** from HTTP Request
- Search "Gmail"
- Select "Gmail"
- Click **Connect** (authenticate with your Gmail)
- To: `pv.rohith96@gmail.com`
- Subject: `Job Brief: {{$node.Code.json.company}}`
- Body:
```
Score: {{$node["HTTP Request2"].json.score}}/5
Fit: {{$node["HTTP Request2"].json.assessment}}

Gaps: {{$node["HTTP Request2"].json.gaps.join(", ")}}
```
- Save

#### Node 6: Save to Tracker
- Click **+** from Gmail
- Search "Write to File"
- Select "Write to File"
- File Path: `/workspace/data/jobs-{{$now.format("YYYY-MM-DD")}}.json`
- Data: `{{$json}}`
- Save

### Step 12: Test Manual Workflow

1. In n8n, click **Execute Workflow** (blue play button)
2. In modal, paste a real job URL
3. Click **Execute**
4. Watch execution in right panel
5. Check email for result

---

### Step 13: Create Second Workflow — Weekly Scanner

This scans job portals weekly (Friday 9am).

**In n8n UI:**

1. Click **New Workflow**
2. Name: `weekly-job-scan-and-email`
3. Add nodes:

#### Node 1: Cron Trigger
- Search "Cron"
- Cron Expression: `0 9 * * 3` (Wed 9am)
- Timezone: `America/Los_Angeles`

#### Node 2: HTTP Request (scan)
- Search "HTTP Request"
- Method: **GET**
- URL: `http://localhost:3001/scan`

#### Node 3: Filter (relevance)
- Search "Item Lists" → "Filter"
- Keep items where:
  - `company` contains `title_keywords`
  - `description` contains `domain_keywords`

#### Node 4: Loop through jobs
- Search "Loop Over Items"
- Items: From Node 3

Inside loop:
- **Node 4a:** HTTP Request (evaluate each job)
- **Node 4b:** Gmail (send email for each job)
- **Node 4c:** Write to tracker file

#### Node 5: Summary Email
- Send final email with count:
  - Jobs found: X
  - Relevant: Y
  - Emails sent: Z

**Save & Enable Schedule:**
1. In workflow, click the Cron trigger
2. Toggle **Active** (on)
3. Save workflow

---

## Phase 5: Testing

### Step 14: Test Manually

```bash
# Test scan script
node scripts/scan-wrapper.mjs

# Expected output:
# [scan-wrapper] Starting job scan...
# [scan-wrapper] Found X jobs from portals
```

### Step 15: Test Evaluate Script

```bash
# Test evaluator
node scripts/evaluate-job.mjs
```

### Step 16: Run Manual Workflow

1. Open n8n UI
2. Workflows → `manual-job-brief`
3. Click **Execute Workflow**
4. Paste a real job URL (e.g., from https://jobs.stripe.com)
5. Check your email for resume brief

### Step 17: Dry-Run Scanner

1. Open n8n UI
2. Workflows → `weekly-job-scan-and-email`
3. Click **Execute Workflow** (manual run)
4. Watch logs
5. Check email for results

---

## Phase 6: Production

### Step 18: Set Up Gmail (Optional)

For email to work, authenticate Gmail:

1. In n8n, go **Settings → Credentials**
2. Click **New** → Search "Gmail"
3. Click **Connect** button
4. Authenticate with Google account
5. Grant permissions
6. Save

**Alternative: App Password**
1. Go https://myaccount.google.com/apppasswords
2. Select Mail + macOS
3. Copy 16-char password
4. In .env.local: `GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx`

### Step 19: Set Up Google Docs (Optional)

For auto-creating resume briefing documents:

1. Create Google Cloud project: https://console.cloud.google.com
2. Enable Google Docs API + Google Drive API
3. Create Service Account → Download JSON key
4. Save key to `./credentials/google-service-account.json`
5. Create Google Drive folder
6. Share folder with service account email
7. In n8n: Settings → Credentials → New → Google Docs
8. Paste JSON key

### Step 20: Enable Weekly Schedule

1. Open n8n UI
2. Workflows → `weekly-job-scan-and-email`
3. Click Cron trigger
4. Toggle **Active** (on)
5. Set time: `0 9 * * 5` (Friday 9am)
6. Save

**n8n must stay running 24/7 for schedule to work:**
```bash
# Keep running
docker-compose up -d
```

### Step 21: Monitor & Iterate

**Every week:**
1. Check emails for job briefs
2. Review scores
3. Apply to promising ones
4. Update `data/applications.md` with results

**Every month:**
1. Edit `config/profile.yml` if roles/keywords change
2. Update `config/cv.md` with new achievements
3. Edit `config/portals.yml` to add/remove companies
4. Tune relevance filters

---

## Summary Checklist

### ✅ Setup Complete When:

- [ ] Docker running locally
- [ ] n8n accessible at http://localhost:5678
- [ ] Admin account created
- [ ] `config/profile.yml` customized with YOUR info
- [ ] `config/cv.md` has YOUR resume
- [ ] `config/portals.yml` lists YOUR target companies
- [ ] Manual workflow created & tested
- [ ] Scan workflow created
- [ ] First manual test run shows email result
- [ ] Gmail credentials added (optional)
- [ ] Weekly schedule enabled (optional)

### ✅ Production Ready When:

- [ ] All checklist above complete
- [ ] Tested with 3-5 real job URLs
- [ ] Gmail integration working
- [ ] Weekly schedule active
- [ ] Monitoring emails arrive
- [ ] `data/applications.md` tracks results

---

## Troubleshooting

### "Docker won't start"
```bash
# Make sure Docker Desktop is open (macOS)
# Or check daemon (Linux): sudo service docker start
docker ps
```

### "n8n won't load"
```bash
# Check logs
docker-compose logs n8n

# Restart
docker-compose down
docker-compose up -d
```

### "Scripts not found"
```bash
# Make sure you're in right directory
pwd
# Should be: /Users/rohith/Downloads/Github/job-search-automation

# Check scripts exist
ls -la scripts/
```

### "Gmail not sending"
```bash
# Check credentials in n8n Settings
# Verify app password (if using)
# Check spam folder
```

### "Jobs not found"
```bash
# Edit config/portals.yml
# Verify portal URLs are correct
# Check title_keywords match real job titles
```

---

## Next Steps After Setup

1. **Weekly automation:** Let it run every Friday 9am
2. **Monthly refinement:** Update profile when targeting changes
3. **Track outcomes:** Mark jobs as "Interview" or "Rejected" in tracker
4. **Learn patterns:** System gets smarter as you mark outcomes
5. **Share repo:** Others can fork and customize

---

## Command Reference

```bash
# Start system
docker-compose up -d

# Stop system
docker-compose down

# View logs
docker-compose logs -f n8n

# Check status
docker-compose ps

# Access n8n
open http://localhost:5678

# Test scripts
node scripts/scan-wrapper.mjs
node scripts/evaluate-job.mjs
node scripts/dedup-jobs.mjs
node scripts/resume-tweaker.mjs

# View tracker
cat data/applications.md

# View profile
cat config/profile.yml

# Git operations
git status
git add .
git commit -m "message"
git push
```

---

## Getting Help

1. **Setup issues:** See SETUP.md
2. **Architecture:** See README.md
3. **Decoupling:** See STANDALONE.md
4. **Deployment:** See GITHUB_DEPLOYMENT.md
5. **Quick start:** See QUICKSTART.md

---

**That's it! You now have a fully functional job search automation system running locally with n8n.** 🚀

