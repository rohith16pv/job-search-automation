# Deploy to GitHub

## One-Time Setup: Create GitHub Repo

### Option 1: GitHub CLI (Recommended)

```bash
# Authenticate with GitHub (opens browser)
gh auth login

# When prompted, select:
# - Hostname: github.com
# - Protocol: HTTPS
# - Authenticate with: Paste an authentication token
#   OR: Login with web browser

# Then create and push repo
cd /Users/rohith/Downloads/Github/job-search-automation
gh repo create job-search-automation --public --source=. --remote=origin --push
```

### Option 2: Manual GitHub UI + Git

1. **Create repo on GitHub:**
   - Go to https://github.com/new
   - Repository name: `job-search-automation`
   - Description: `Standalone n8n job search automation engine`
   - Visibility: **Public**
   - Click **Create repository**

2. **Push your local code:**
   ```bash
   cd /Users/rohith/Downloads/Github/job-search-automation
   
   git remote add origin https://github.com/YOUR_USERNAME/job-search-automation.git
   git branch -M main
   git push -u origin main
   ```

### Option 3: GitHub Desktop App

1. Create repo on https://github.com/new (same as Option 2)
2. Open GitHub Desktop
3. File → Clone Repository → select `job-search-automation`
4. It will pull your local repo and sync

---

## After Deployment

Once deployed to GitHub:

```bash
# Verify remote
git remote -v

# Expected output:
# origin  https://github.com/YOUR_USERNAME/job-search-automation.git (fetch)
# origin  https://github.com/YOUR_USERNAME/job-search-automation.git (push)

# View your repo
open https://github.com/YOUR_USERNAME/job-search-automation
```

---

## What Gets Pushed

```
job-search-automation/
├── config/                 ← Your customization templates
├── data/                   ← Tracker (applications.md)
├── scripts/                ← n8n helper scripts
├── docker-compose.yml
├── package.json
├── README.md
├── SETUP.md
├── QUICKSTART.md
├── STANDALONE.md
└── ... (other docs & config)
```

**NOT pushed:**
- `.env.local` (secrets)
- `node_modules/`
- `.n8n/` (Docker volume)
- Generated scan history (auto-generated)

---

## GitHub Actions (Optional)

Once deployed, you can add automated workflows:

```yaml
# .github/workflows/test.yml
name: Test Configuration
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Validate YAML
        run: |
          # Validate config files
          npm install -g yaml-lint
          yaml-lint config/*.yml
```

---

## Sharing with Others

Once on GitHub, others can:

```bash
# Clone your repo
git clone https://github.com/YOUR_USERNAME/job-search-automation

# Or fork it to customize for themselves
# (Fork button on GitHub UI)
```

---

## Environment Variables

After cloning, remind users to:

```bash
cp .env.example .env.local
# Edit .env.local with their credentials
```

---

## Next: GitHub Pages Documentation (Optional)

If you want a public docs site:

1. Enable GitHub Pages in repo settings
2. Select `main` branch, `/docs` folder
3. Build docs from README.md

---

**Choose your deployment method above and follow the steps!**

