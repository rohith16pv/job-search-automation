# Quick Start (5 Minutes)

## TL;DR for Impatient

```bash
# 1. Clone repo (already done)
cd /Users/rohith/Downloads/Github/job-search-automation

# 2. Copy env template
cp .env.example .env.local
# Edit .env.local: add CAREER_OPS_PATH, GMAIL credentials

# 3. Start Docker
docker-compose up -d && sleep 15

# 4. Open browser
open http://localhost:5678

# 5. First run: set email + password

# 6. Add Gmail credential (Settings → Credentials → Gmail → OAuth)

# 7. Done!
```

## In 30 Seconds After That

### Option A: Test Manual Job Brief
1. n8n: Workflows → Create new
2. Add trigger: Manual
3. Add HTTP Request: fetch job HTML
4. Add Gmail: send to yourself
5. Click Execute, paste job URL
6. Check email

### Option B: Run career-ops scan
1. Create workflow with Manual trigger
2. Add "Execute Command" node
3. Command: `node /workspace/career-ops/scan.mjs --json`
4. Execute → see jobs

### Option C: Run now (use your existing career-ops)
```bash
cd ../career-ops
/career-ops scan  # Already works!
```

## Full Setup (30 Minutes)

Follow SETUP.md for:
1. Gmail App Password
2. Google Docs API (optional)
3. Credential setup
4. Workflow creation
5. Scheduling

## What You Get

- **Manual:** Paste job URL → get resume brief + email draft
- **Weekly:** Friday 9am → scan portals → email top 5 jobs with brief
- **Scheduled apply:** Daily → queue up pre-approved applications
- **Feedback loop:** Track interviews → learn what works

## Common First Mistakes

1. **"n8n won't start"** → Docker not running. Open Docker Desktop.
2. **"Cannot find career-ops"** → Update CAREER_OPS_PATH in .env.local
3. **"Gmail fails"** → Use App Password, not main password
4. **"Workflows stuck"** → n8n needs 24/7 uptime for scheduling. Use `docker-compose up -d`

## Next: Connect to career-ops

This automation is read-only on career-ops. After workflows email you:

```bash
cd ../career-ops
node merge-tracker.mjs  # Imports batch results
git status             # See new applications
```

---

**That's it.** You now have a local job automation engine that doesn't touch career-ops.

