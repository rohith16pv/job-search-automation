# Job Search Automation

A fully automated daily job search pipeline built for **Senior PMs in Payments / Fintech**. Scouts 11 job sources, AI-scores every posting against your resume, and for strong matches creates a tailored Google Doc resume — surgical text replacements, bold key metrics, yellow highlights for review.

---

## How it works

```
/job-auto-scan
  └─ 11 scouts fire in parallel
      └─ Greenhouse · Lever · Ashby · SmartRecruiters · Wellfound
         Workday · Google Careers · Amazon Jobs · Apple Jobs
         LinkedIn · Indeed (via Apify)
  └─ Dedup + hard filters (USA only, configurable recency window)
  └─ Claude AI scores each job (your Claude subscription, two-pass)
  └─ Routes to Google Sheets
      ├─ P0 Hot Leads  (score ≥ 70)
      ├─ P1 Jobs       (score 50–69)
      └─ P2 Review     (score 40–49, borderline)
  └─ Saves data/jobs_store.json  ← persistent, never overwritten

/job-auto-resume-p0
  └─ Reads jobs_store.json → filters P0 jobs without a GDoc yet
  └─ For each: Claude generates surgical replacements (1 summary + 4 bullets)
  └─ Copies base resume GDoc (fonts + layout preserved)
  └─ Applies replaceAllText, bolds metrics, yellow highlights, blue reorder hint
  └─ Updates Resume GDoc (col K), ATS Post-Mod Score (col G), Status in "P0 Hot Leads"

/job-auto-resume-p1
  └─ Same as above but for P1 jobs → updates "P1 Jobs" tab
```

---

## Configured for: Rohith Purimetla Vinay

### Profile (`config/profile.yml`)

| Field | Value |
|---|---|
| Name | Rohith Purimetla Vinay |
| Location | San Francisco Bay Area, CA |
| Current Title | Senior Product Manager |
| Experience | 8 years |
| Industry | Payments, Fintech, Money Movement |

### Target roles (scored as P0/P1)

`Senior Product Manager` · `Senior PM` · `Sr. PM` · `Product Manager II` · `Technical PM` · `Product Manager, Platform` · `Product Manager, Growth` · `Staff Product Manager` · `Principal Product Manager` · `Lead Product Manager`

### Scoring (`config/scoring.yml`)

| Category | Points |
|---|---|
| Title match (Senior PM / Staff PM) | 20 |
| Domain keywords (payments, ACH, RTP, embedded finance…) | up to 35 |
| Skills match (API, platform, B2B, compliance, fraud…) | up to 25 |
| Seniority signals (5+ years, senior, technical PM…) | up to 15 |
| Location (remote > hybrid > US onsite) | up to 5 |

**Auto-rejected (score = 0):** Director / VP / Head of Product / Associate PM / Engineering / Sales / Marketing roles.

**Routing:** ≥ 70 → P0 Hot Leads + tailored GDoc · 50–69 → P1 backlog · < 50 → dropped

### Companies being scouted

**Greenhouse (52 companies)**
Stripe · Plaid · Brex · Affirm · Marqeta · Chime · Checkout.com · Payoneer · Nuvei · Spreedly · Lithic · Parafin · Pinwheel · Moov · Lyft · Airbnb · DoorDash · Instacart · Nubank · Betterment · Upgrade · Coinbase · BitGo · Flywire · Synctera · Treasury Prime · Bill.com · Databricks · Scale AI · Uber Freight · Finix · Highnote · Orum · Cross River Bank · Sardine · Ripple · Tipalti · Deel · Papaya Global · Rain · Argyle · Bitso · Banked · i2c · Toast · Shopify · Rippling · Gusto · Benchling · Lattice · Checkr · Robinhood

**Lever (27 companies)**
Adyen · Block · Square · Robinhood · SoFi · Ramp · Modern Treasury · Mercury · Column · Unit · Greenlight · PayItOff · Sila · Klarna · Revolut · Plaid · Nium · CurrencyCloud · Dwolla · Narmi · Anchorage · Coupa · Spreedly · Brex · Stripe · Vercel · Stytch

**Ashby (21 companies)**
Astra · Payrails · Ramp · Modern Treasury · Mercury · Column · Unit · Lithic · Parafin · Dave · Acorns · Airwallex · Checkout.com · Slope · Arc · Vercel · Stytch · Linear · Retool · Anthropic · OpenAI

**SmartRecruiters (8 companies)**
PayPal · Western Union · MoneyGram · Remitly · Wise · NerdWallet · Intuit

**Workday (10 companies)**
PayPal · Fiserv · FIS · Mastercard · Visa · Capital One · Fidelity · MX Technologies · JPMorgan Chase · Citi

**Direct APIs**
Google Careers · Amazon Jobs · Apple Jobs

**Apify scrapers**
LinkedIn (8 search queries) · Indeed (4 search queries)

### AI resume tailoring

Every P0 resume is tailored with company-specific vocabulary for 20+ companies:

| Company | Known vocabulary injected |
|---|---|
| Stripe | payment infrastructure, global payments network, API-first platform |
| Plaid | financial data network, open finance, consumer-permissioned data |
| Coinbase | crypto economy, onchain financial system, stablecoin infrastructure |
| Capital One | data-driven bank, machine learning at scale, real-time decisioning |
| Brex | spend management, corporate cards, embedded finance, financial OS |
| Mercury | banking for startups, treasury management, API banking |
| Ramp | corporate spend management, finance automation, accounts payable |
| Adyen | unified commerce platform, acquiring, issuing, enterprise merchants |
| Visa | global payment network, Visa Direct, push payments, network tokenization |
| Mastercard | multi-rail strategy, real-time push payments, open banking |
| + 10 more | Chime · Affirm · Robinhood · Klarna · JPMorgan · PayPal · Square · Fiserv · Marqeta · Wise · Nium |

**Anti-AI-slop rules:** 25+ banned phrases, no em dashes, action-verb-led bullets, must sound human when read aloud. Each replacement cites an exact JD phrase as anchor.

**Formatting applied to every GDoc:**
- 🟡 Yellow = paragraph was AI-rewritten (review before sending)
- 🔵 Blue = this bullet should move to position #1 for this JD (manual, 2 seconds)
- **Bold** = key metric or JD-anchor term within each bullet
- Skills section: heading bold only (`Domain:`, `Product:`, `Technical & AI:`)

---

## Scout health & sanity checks

Every scan prints a per-source table so broken scouts are immediately visible:

```
  ┌─────────────────────────────┬────────┬────────┐
  │ Source                      │  Jobs  │ Status │
  ├─────────────────────────────┼────────┼────────┤
  │ greenhouse                  │    193 │ OK     │
  │ linkedin                    │    285 │ OK     │
  │ indeed                      │    200 │ OK     │
  │ wellfound                   │      0 │ WARN   │
  ...
  │ TOTAL                       │    850 │        │
  └─────────────────────────────┴────────┴────────┘
  ⚠  1 scout(s) returned 0 jobs — actor may be broken or misconfigured.
```

- **WARN** — scout ran but returned 0 jobs; actor ID or field mapping may be stale
- **ERROR** — scout threw an exception; full error is printed inline
- **Hard abort** — if total raw jobs < 10, the pipeline stops before scoring to avoid wasting Claude usage

---

## Setup

### Prerequisites

```bash
pip install -r requirements.txt
```

### 1. Run the onboarding checker

```bash
python3 scripts/onboard.py
```

This validates every integration and tells you exactly what to fix.

### 2. What you need

| Credential | Where to get it | .env key |
|---|---|---|
| Claude Code login | [claude.com/claude-code](https://claude.com/claude-code) — uses your Claude subscription, run `claude` once to log in | _(none — no API key)_ |
| Base resume Google Doc ID | From URL of your resume GDoc | `RESUME_GDOC_ID` |
| Google Sheets ID | From URL of your tracking sheet | `GOOGLE_SHEETS_ID` |
| Google Drive folder ID | Create a folder, share with service account | `GOOGLE_DRIVE_FOLDER_ID` |
| Service account JSON | Google Cloud Console → IAM → Service Accounts | `GOOGLE_SERVICE_ACCOUNT_JSON` |
| OAuth credentials JSON | Google Cloud Console → APIs → Credentials → Desktop App | `GOOGLE_OAUTH_CREDENTIALS` |
| Apify API key | [apify.com](https://apify.com) — free tier | `APIFY_API_KEY` |
| Notion token (optional) | [notion.so/my-integrations](https://www.notion.so/my-integrations) | `NOTION_API_TOKEN` |

### 3. Authorize Google (one-time)

```bash
python3 scripts/authorize_google.py
```

Generates `config/google_token.json` so the pipeline can read your resume and create GDocs in your Drive.

Share your **base resume** and **Drive folder** with the service account:
```
job-hunt@project-job-automation-498906.iam.gserviceaccount.com
```

---

## Running the pipeline

### Via Claude slash commands (recommended)

```
/job-auto-scan           # Step 1: scout + score + write to Sheets
/job-auto-resume-p0      # Step 2a: create GDocs for P0 hot leads
/job-auto-resume-p1      # Step 2b: create GDocs for selected P1 jobs
/job-auto-run            # Both steps back-to-back
```

### Via command line

```bash
python3 orchestrator.py --scan-only     # Step 1
python3 orchestrator.py --resume-only   # Step 2a (P0)
python3 orchestrator.py --resume-p1     # Step 2b (P1)
python3 orchestrator.py                 # Full pipeline
python3 orchestrator.py --dry-run       # Preview scoring, no writes
```

### Test with 2 hardcoded jobs

```bash
python3 test_e2e.py
```

---

## Data + storage

| Location | What it is |
|---|---|
| `data/jobs_store.json` | Persistent job store — accumulates across all scans, never overwritten. Keyed by job ID. Preserves GDoc URLs so re-scanning doesn't re-create resumes. |
| `data/seen_jobs.jsonl` | Dedup log — job IDs already processed so the same posting isn't re-scored on the next run. |
| `data/tailored/` | Fallback markdown briefs (created when GDoc creation fails). |
| `config/google_token.json` | OAuth token — refresh automatically. Gitignored. |
| `config/google_service_account.json` | Service account key. Gitignored. |

---

## Google Sheets columns

Both `P0 Hot Leads` and `P1 Jobs` tabs share the same schema:

| Col | Field | Notes |
|---|---|---|
| A | Posted Date | When the role was posted (from the job board) |
| B | Date Added | When the row was written to the sheet |
| C | Company | |
| D | Role | Job title |
| E | Status | `New` → `Resume Ready` (auto) → update manually as you progress |
| F | ATS Pre-Score | Fitment score 0–100 from the scoring pass |
| G | ATS Post-Mod Score | JD keyword coverage % after resume tailoring |
| H | Location | |
| I | Portal Source | Which scout found it |
| J | Job Link | Direct link to posting |
| K | Resume GDoc | Filled by `/job-auto-resume-*` |
| L | Notes | Salary (if listed) lands here; rest is yours |

Tabs still on the old 10-column layout are migrated in place automatically on the next write.

---

## Customisation

### Add a company to scout

Edit `config/job_sources.yml` — add the company slug under its ATS:
```yaml
greenhouse:
  - your-company-slug   # from boards.greenhouse.io/YOUR-SLUG
```

### Tune scoring

Edit `config/scoring.yml` — adjust keyword weights, add domain terms, change routing thresholds.

### Update your profile

Edit `config/profile.yml` — name, target roles, location preferences, compensation target.

### Add company vocabulary for tailoring

Edit `core/claude_client.py` → `_COMPANY_PROFILES` dict — add the company's known language so tailoring uses their exact terminology.

---

## Architecture

```
orchestrator.py          Main entry point (--scan-only, --resume-only, --resume-p1)
agents/
  scout_greenhouse.py    }
  scout_lever.py         }
  scout_ashby.py         } 11 scouts — all async, fire in parallel
  scout_smartrecruiters  }
  scout_workday.py       }
  scout_google_careers   }
  scout_amazon_jobs.py   }
  scout_apple_jobs.py    }
  scout_linkedin.py      } Apify (sync, run in threads)
  scout_indeed.py        }
  scout_wellfound.py     }
core/
  health.py              Daily sanity checks: preflight, scout baselines, ATS slug audit
  improve.py             Self-improvement: board auto-discovery, blocked-title log, weekly Claude review
  scorer.py              Keyword pre-score → Claude AI deep score
  claude_client.py       Claude client (claude CLI, subscription): scoring + two-pass resume tailoring
  resume_tailor.py       Orchestrates GDoc creation from Claude replacements
  dedup.py               Job ID deduplication against seen_jobs.jsonl
  filters.py             Hard filters: USA-only, configurable recency window (default 20 days)
integrations/
  google_docs.py         Read base resume · Copy + edit GDoc · Bold + highlight
  google_sheets.py       Append rows (A–L schema) · Update GDoc URL, post-mod score, status
  notion_client.py       Mirror P0/P1 to Notion databases (optional)
config/
  profile.yml            Your name, targets, compensation
  job_sources.yml        Companies per ATS
  scoring.yml            Weights, keywords, routing thresholds
scripts/
  onboard.py             Setup validator — run this first
  authorize_google.py    One-time OAuth flow
.claude/commands/
  job-auto-scan.md       /job-auto-scan skill
  job-auto-resume-p0.md  /job-auto-resume-p0 skill
  job-auto-resume-p1.md  /job-auto-resume-p1 skill
  job-auto-run.md        /job-auto-run skill
```

---

## What's gitignored

```
.env
config/google_service_account.json
config/google_token.json
config/google_oauth_credentials.json
data/jobs_store.json
data/seen_jobs.jsonl
data/tailored/
```

Never commit credentials. The `.env.example` file shows the shape without real values.
