# Quick Start (5 Minutes)

## TL;DR for Impatient

```bash
# 1. Go to repo
cd /Users/rohith/Downloads/Github/job-search-automation

# 2. Copy env template
cp .env.example .env.local
# Edit .env.local: add GMAIL_EMAIL + GMAIL_APP_PASSWORD

# 3. Start Docker
docker-compose up -d && sleep 15

# 4. Open browser
open http://localhost:5678

# 5. First run: set admin email + password

# 6. Add Gmail credential (Settings → Credentials → New → Gmail)

# 7. Done! All data is local.
```

## In 30 Seconds After That

### Option A: Test Manual Job Brief
1. n8n: Workflows → Create new
2. Add trigger: Manual
3. Add HTTP Request: fetch job HTML
4. Add Gmail: send to yourself
5. Click Execute, paste job URL
6. Check email for resume brief

### Option B: Run scanner
1. Create workflow with Manual trigger
2. Add "Execute Command" node
3. Command: `node /workspace/scripts/scan-wrapper.mjs`
4. Execute → see jobs in logs

### Option C: All data is local
```bash
cat config/profile.yml       # Your profile
cat config/cv.md            # Your resume
cat config/portals.yml      # Job sources
cat data/applications.md    # Tracker
```

## Full Setup (30 Minutes)

Follow SETUP.md for:
1. Gmail App Password setup
2. Google Docs API (optional, for resume briefing docs)
3. Add credentials in n8n UI
4. Create workflows
5. Set cron schedules

## What You Get

- **Manual:** Paste job URL → get resume brief + email draft
- **Weekly:** Friday 9am → scan your configured portals → email top 5 relevant jobs
- **Scheduled apply:** Daily → queue applications (you approve before submit)
- **Feedback loop:** Mark outcomes (interview/rejected/offer) → system learns what works

## Common First Mistakes

1. **"n8n won't start"** → Docker not running. Open Docker Desktop.
2. **"Cannot read config/cv.md"** → Make sure you're in the right directory
3. **"Gmail fails"** → Use App Password, not main password
4. **"Workflows stuck"** → n8n needs 24/7 uptime for cron scheduling. Use `docker-compose up -d`

## Your Data Stays Local

All your profile, resume, and tracking data lives in `config/` and `data/`:
- ✅ No external service dependencies
- ✅ Can work completely offline
- ✅ Can be backed up with git

```bash
git init
git add config/ data/
git commit -m "Initial setup"
```

---

**That's it.** You have a fully standalone job automation engine that never touches any external systems.

