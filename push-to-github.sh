#!/bin/bash

# Push job-search-automation to GitHub
# This script automates the deployment process

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║      Job Search Automation — GitHub Deployment                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) not found."
    echo "   Install with: brew install gh"
    exit 1
fi

# Check authentication
echo "🔐 Checking GitHub authentication..."
if ! gh auth status &> /dev/null; then
    echo "❌ Not authenticated. Logging in..."
    echo ""
    gh auth login
    echo ""
fi

# Get username
USERNAME=$(gh api user -q '.login')
echo "✅ Authenticated as: $USERNAME"
echo ""

# Check if repo exists
REPO_URL="https://github.com/$USERNAME/job-search-automation"
echo "📦 Checking if repo exists at: $REPO_URL"

if gh api "repos/$USERNAME/job-search-automation" &> /dev/null; then
    echo "✅ Repo already exists."
    echo "   Updating remote..."
    git remote remove origin 2>/dev/null || true
    git remote add origin "https://github.com/$USERNAME/job-search-automation.git"
else
    echo "📝 Creating new public repo..."
    gh repo create job-search-automation \
        --public \
        --description "Standalone n8n job search automation engine" \
        --source=. \
        --remote=origin \
        --push
    echo "✅ Repo created and code pushed!"
    exit 0
fi

echo ""
echo "🚀 Pushing code to GitHub..."
git branch -M main
git push -u origin main

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    ✅ DEPLOYMENT COMPLETE!                    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "📍 Your repo is now live at:"
echo "   $REPO_URL"
echo ""
echo "📚 Next Steps:"
echo "   1. Visit: $REPO_URL"
echo "   2. Share the link with others"
echo "   3. They can clone with:"
echo "      git clone $REPO_URL.git"
echo ""
echo "💡 To customize further:"
echo "   - Edit README.md on GitHub UI or locally"
echo "   - Add GitHub Actions workflows in .github/workflows/"
echo "   - Enable GitHub Pages for documentation"
echo ""
