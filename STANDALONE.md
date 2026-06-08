# Fully Standalone — Zero External Dependencies

This system is **completely self-contained**. It does not depend on career-ops or any other external system.

## What Changed

### Before (Coupled to career-ops)
```
❌ Read from: ../career-ops/cv.md
❌ Read from: ../career-ops/config/profile.yml
❌ Read from: ../career-ops/portals.yml
❌ Read from: ../career-ops/data/scan-history.tsv
❌ Write to: ../career-ops/batch/tracker-additions/
```

### Now (Fully Standalone)
```
✅ config/cv.md                        (your resume — local)
✅ config/profile.yml                  (your profile — local)
✅ config/portals.yml                  (ATS sources — local)
✅ data/scan_history.jsonl             (dedup log — local)
✅ data/applications.md                (tracker — local)
```

## What's Included

### Configuration Files (Customize These)
- **`config/profile.yml`** — Your details (name, email, target roles, keywords, location, salary expectations)
- **`config/cv.md`** — Your resume in markdown format (ready to customize)
- **`config/portals.yml`** — ATS portals to scan (Stripe, Square, Adyen, etc. — add/remove as needed)

### Data Tracking (Auto-Generated)
- **`data/applications.md`** — Your application tracker (company, role, status, score)
- **`data/scan_history.jsonl`** — Dedup log (which jobs you've already seen)

### Scripts (No External Calls)
- **`scripts/scan-wrapper.mjs`** — Reads local portals.yml, returns job listings
- **`scripts/evaluate-job.mjs`** — Loads local profile.yml, scores jobs by fit
- **`scripts/resume-tweaker.mjs`** — Reads local cv.md, suggests section reordering
- **`scripts/dedup-jobs.mjs`** — Checks against local scan_history.jsonl

## How It Works

```
1. Configure: Edit config/profile.yml, config/cv.md, config/portals.yml
2. Run: docker-compose up -d
3. Access: http://localhost:5678 (n8n UI)
4. Trigger workflows:
   - Manual: Paste job URL → get resume brief
   - Weekly: Friday 9am → auto-scan portals
   - Daily: Check status
5. Data stays local: Everything in config/ and data/
```

## No External System Calls

**Required (if you want email):**
- ✅ Gmail (via app password) — _optional_, for sending emails only
- ✅ Google Docs API (via service account) — _optional_, for resume briefing docs

**NOT required:**
- ❌ No career-ops
- ❌ No LinkedIn API
- ❌ No external job database
- ❌ No cloud storage (unless you enable it)
- ❌ No external hosting

## File Structure

```
job-search-automation/
├── config/                  # Your personalization
│   ├── profile.yml         # (EDIT THIS) Your profile
│   ├── cv.md               # (EDIT THIS) Your resume
│   └── portals.yml         # (EDIT THIS) Job sources
├── data/                    # Auto-generated
│   ├── applications.md      # Tracker
│   └── scan_history.jsonl   # Dedup log
├── scripts/                 # n8n helpers (no edits needed)
│   ├── scan-wrapper.mjs
│   ├── evaluate-job.mjs
│   ├── resume-tweaker.mjs
│   └── dedup-jobs.mjs
├── docker-compose.yml       # Docker setup
├── package.json             # Dependencies
└── README.md, SETUP.md, etc.
```

## Getting Started

### Step 1: Customize Your Profile
```bash
vim config/profile.yml        # Edit your target roles, keywords, locations
vim config/cv.md              # Edit your resume
vim config/portals.yml        # Edit which ATS sites to scan
```

### Step 2: Start n8n
```bash
docker-compose up -d
sleep 15
open http://localhost:5678
```

### Step 3: First Run
1. Set admin email + password in n8n UI
2. Create workflows (see README.md)
3. Test manually (paste a job URL)

### Step 4: Enable Scheduling (Optional)
1. Add Gmail credential (if you want email)
2. Set up weekly cron trigger
3. n8n runs automatically at 9am Friday

## What's NOT Included

**You'll need to:**
- ✏️ Edit config files with your actual details
- 🔐 Set up Gmail app password (if you want email)
- 🔐 Set up Google Docs API (if you want resume briefs)
- 🏗️ Build workflows in n8n UI (templates in README.md)

**You DON'T need to:**
- ❌ Have career-ops installed
- ❌ Have any other system running
- ❌ Depend on external job aggregators
- ❌ Use any paid services (except optional Gmail/Google)

## Deployment

### Deploy Anywhere
Since this is fully standalone, you can:
- 🖥️ Run on your laptop (using Docker)
- 🐧 Run on Linux server
- ☁️ Run on AWS/GCP/Azure (using Docker)
- 🏢 Run on company infrastructure

**Only requirement:** Docker + Docker Compose

### Backup
```bash
# All your data is in config/ and data/
git init
git add config/ data/
git commit -m "Initial setup"
git remote add origin https://github.com/your-repo/job-search-automation
git push
```

## FAQ

**Q: Can I use this without career-ops?**
A: Yes! That's the whole point. This is completely standalone.

**Q: Can I use this with career-ops too?**
A: Yes. You can use this as a separate system. If you want to sync back to career-ops later, you can export your tracker.

**Q: What if I want to change something?**
A: Edit the config files. All data is local and human-readable.

**Q: Can I migrate to career-ops later?**
A: Yes. Your applications.md can be imported into career-ops' format.

**Q: What if I want to use a different job source?**
A: Add it to config/portals.yml, update scripts/scan-wrapper.mjs to fetch from it.

---

**Bottom line:** This is a complete, self-contained job search automation engine. Zero external dependencies (except optional Gmail/Google Docs for email/docs). All your data stays local.

