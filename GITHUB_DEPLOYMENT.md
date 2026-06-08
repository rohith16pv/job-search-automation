# Deploy to GitHub — Complete Guide

Your `job-search-automation` repo is ready to deploy. Choose your method below.

## 🚀 Option 1: Automatic Deployment (Recommended)

Easiest method — just run the script:

```bash
cd /Users/rohith/Downloads/Github/job-search-automation

# Make script executable (if not already)
chmod +x push-to-github.sh

# Run deployment
./push-to-github.sh
```

**What it does:**
1. Checks GitHub CLI is installed
2. Authenticates you with GitHub (if needed)
3. Creates repo `job-search-automation` on your GitHub account
4. Pushes all code
5. Shows you the URL

**Result:** Your code is live at `https://github.com/YOUR_USERNAME/job-search-automation`

---

## 🔐 Option 2: Manual GitHub CLI

If the script doesn't work:

```bash
# Step 1: Authenticate
gh auth login
# Select: github.com → HTTPS → Paste token
# (Or choose "Login with web browser")

# Step 2: Create repo
cd /Users/rohith/Downloads/Github/job-search-automation
gh repo create job-search-automation --public --source=. --remote=origin --push
```

---

## 🌐 Option 3: Manual Web + Git

If you prefer the GitHub UI:

1. **Create repo on GitHub:**
   - Go to https://github.com/new
   - Repository name: `job-search-automation`
   - Description: `Standalone n8n job search automation engine`
   - Visibility: **Public**
   - Click **Create repository**

2. **Push from terminal:**
   ```bash
   cd /Users/rohith/Downloads/Github/job-search-automation
   
   git remote add origin https://github.com/YOUR_USERNAME/job-search-automation.git
   git branch -M main
   git push -u origin main
   ```

---

## ✅ Verify Deployment

After deploying, verify your repo is live:

```bash
# Check remote
git remote -v

# Should show:
# origin  https://github.com/YOUR_USERNAME/job-search-automation.git (fetch)
# origin  https://github.com/YOUR_USERNAME/job-search-automation.git (push)

# Open in browser
open https://github.com/YOUR_USERNAME/job-search-automation
```

---

## 📦 What Gets Deployed

```
✅ Deployed:
├── config/          (CV, profile, portals templates)
├── data/            (application tracker)
├── scripts/         (n8n helper scripts)
├── .github/         (issue templates, PR template)
├── docker-compose.yml
├── package.json
├── *.md files       (documentation)
├── LICENSE          (MIT)
└── push-to-github.sh

❌ NOT Deployed:
├── .env.local       (secrets, ignored)
├── node_modules/    (installed on-demand)
├── .n8n/            (Docker volume)
├── Anything in .gitignore
```

---

## 🎯 What to Do After Deployment

### 1. Share the Link
```
Share this with others:
https://github.com/YOUR_USERNAME/job-search-automation
```

### 2. They Can Clone It
```bash
git clone https://github.com/YOUR_USERNAME/job-search-automation
cd job-search-automation
cp .env.example .env.local
# (Edit .env.local with their credentials)
docker-compose up -d
```

### 3. Customize README.md
- Edit on GitHub UI (pencil icon)
- Or edit locally and push:
  ```bash
  git add README.md && git commit -m "docs: customize readme" && git push
  ```

### 4. Enable GitHub Pages (Optional)
```bash
# On GitHub: Settings → Pages → Source: main branch /root
# Then your repo has docs at: https://YOUR_USERNAME.github.io/job-search-automation
```

### 5. Add GitHub Actions (Optional)
Add automated tests:
```bash
mkdir -p .github/workflows
# Create config-validation.yml, tests, linting, etc.
```

---

## 🔑 Authentication Troubleshooting

### "gh not found"
```bash
brew install gh
```

### "Not authenticated"
```bash
gh auth login
# Choose: github.com → HTTPS → Login with web browser
```

### "Permission denied" when pushing
```bash
# Make sure you have the right credentials
gh auth status

# If it shows wrong account, re-authenticate
gh auth logout
gh auth login
```

### Using Personal Access Token Instead
```bash
# Generate token at: https://github.com/settings/tokens
# Then:
export GH_TOKEN=your_token_here
gh auth login --with-token < /tmp/token.txt
```

---

## 📊 Repository Status

```
Local repo path:
  /Users/rohith/Downloads/Github/job-search-automation

Git commits:
  5 commits total
  - Initial setup
  - Full decoupling from career-ops
  - Documentation cleanup
  - GitHub templates
  - Deployment script

Current branch: main
Remote: (not yet set, will be set during deployment)
```

---

## 🚀 Quick Deploy Checklist

- [ ] cd to `/Users/rohith/Downloads/Github/job-search-automation`
- [ ] Decide on deployment method (1, 2, or 3 above)
- [ ] Run deployment
- [ ] Verify with `git remote -v`
- [ ] Open URL in browser to confirm
- [ ] Share link with others

---

## 💡 Pro Tips

### Keep Local & Remote in Sync
```bash
# After making changes locally
git add .
git commit -m "your message"
git push

# After making changes on GitHub UI (rare)
git pull
```

### Create Branches for Features
```bash
git checkout -b feature/my-feature
# Make changes
git push -u origin feature/my-feature
# Then open Pull Request on GitHub UI
```

### Add Collaborators
GitHub → Settings → Collaborators → Add people

### Enable Discussions (Optional)
GitHub → Settings → Features → Discussions

---

**Ready to deploy? Run:**

```bash
cd /Users/rohith/Downloads/Github/job-search-automation
./push-to-github.sh
```

**Questions?** See DEPLOY.md

