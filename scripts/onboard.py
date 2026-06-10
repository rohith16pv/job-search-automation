"""
Onboarding + config validator for Job Search Automation.

Run this once before your first scan, and any time something breaks.
It checks every integration, shows what's working, and tells you exactly
how to fix what isn't.

Usage:
    python3 scripts/onboard.py
"""
import json
import os
import sys

# Load .env before anything else
from pathlib import Path
_ROOT = Path(__file__).parent.parent
_ENV  = _ROOT / ".env"
sys.path.insert(0, str(_ROOT))

if _ENV.exists():
    from dotenv import load_dotenv
    load_dotenv(_ENV)
else:
    print("  ⚠️  No .env file found. Copy .env.example to .env and fill in your values.")

# ── Helpers ───────────────────────────────────────────────────────────────────

_OK   = "  ✅"
_FAIL = "  ❌"
_WARN = "  ⚠️ "
_INFO = "  ℹ️ "

_results: list[tuple[str, bool, str]] = []  # (label, passed, note)


def check(label: str, passed: bool, ok_note: str = "", fail_note: str = "") -> bool:
    note = ok_note if passed else fail_note
    icon = _OK if passed else _FAIL
    print(f"{icon}  {label}" + (f"\n       {note}" if note else ""))
    _results.append((label, passed, note))
    return passed


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def env(key: str) -> str:
    return os.environ.get(key, "").strip()


# ── 1. Environment variables ──────────────────────────────────────────────────

section("1 / 7   Environment Variables (.env)")

import shutil as _shutil
check("claude CLI",
      _shutil.which("claude") is not None,
      "Claude CLI found (AI scoring + resume tailoring on your Claude subscription)",
      "Missing — install Claude Code (https://claude.com/claude-code), then run `claude` once to log in")

check("RESUME_GDOC_ID",
      bool(env("RESUME_GDOC_ID")),
      f"Base resume Doc ID: {env('RESUME_GDOC_ID')}",
      "Missing — open your resume Google Doc, copy the ID from the URL, add RESUME_GDOC_ID=... to .env")

check("GOOGLE_SHEETS_ID",
      bool(env("GOOGLE_SHEETS_ID")),
      f"Sheets ID: {env('GOOGLE_SHEETS_ID')}",
      "Missing — create a Google Sheet, copy its ID from URL, add GOOGLE_SHEETS_ID=... to .env")

check("GOOGLE_DRIVE_FOLDER_ID",
      bool(env("GOOGLE_DRIVE_FOLDER_ID")),
      f"Drive folder ID: {env('GOOGLE_DRIVE_FOLDER_ID')}",
      "Missing — create a folder in Google Drive, share it with the service account, add GOOGLE_DRIVE_FOLDER_ID=... to .env")

check("APIFY_API_KEY",
      bool(env("APIFY_API_KEY")),
      "Apify configured (LinkedIn + Indeed scraping)",
      "Missing — get a free key at https://apify.com  →  add APIFY_API_KEY=... to .env")

check("NOTION_API_TOKEN",
      bool(env("NOTION_API_TOKEN")),
      "Notion token configured",
      "Optional — skip if you don't use Notion. Get token at https://www.notion.so/my-integrations")

notion_dbs = bool(env("NOTION_P0_DB_ID") and env("NOTION_P1_DB_ID"))
check("NOTION_P0_DB_ID + NOTION_P1_DB_ID",
      notion_dbs,
      f"P0 DB: {env('NOTION_P0_DB_ID')[:8]}...  P1 DB: {env('NOTION_P1_DB_ID')[:8]}...",
      "Optional — set both NOTION_P0_DB_ID and NOTION_P1_DB_ID in .env")


# ── 2. Config files ───────────────────────────────────────────────────────────

section("2 / 7   Config Files")

sa_path = _ROOT / env("GOOGLE_SERVICE_ACCOUNT_JSON") if env("GOOGLE_SERVICE_ACCOUNT_JSON") else _ROOT / "config/google_service_account.json"
tok_path = _ROOT / env("GOOGLE_TOKEN_PATH") if env("GOOGLE_TOKEN_PATH") else _ROOT / "config/google_token.json"
oauth_path = _ROOT / env("GOOGLE_OAUTH_CREDENTIALS") if env("GOOGLE_OAUTH_CREDENTIALS") else _ROOT / "config/google_oauth_credentials.json"

check("config/google_service_account.json",
      sa_path.exists(),
      "Service account key present",
      f"Missing at {sa_path}\nCreate a service account at https://console.cloud.google.com → IAM → Service Accounts → Keys → JSON")

check("config/google_token.json  (OAuth)",
      tok_path.exists(),
      "OAuth token present (user-owned Drive access)",
      f"Missing — run:  python3 scripts/authorize_google.py\nThis grants Drive/Docs access to store tailored resumes in your Google Drive.")

check("config/google_oauth_credentials.json",
      oauth_path.exists(),
      "OAuth client credentials present",
      "Missing — download Desktop App OAuth client JSON from Google Cloud Console → APIs & Services → Credentials")

check("config/profile.yml",
      (_ROOT / "config/profile.yml").exists(),
      "Candidate profile configured",
      "Missing — copy config/profile.yml from the repo and fill in your details")

check("config/job_sources.yml",
      (_ROOT / "config/job_sources.yml").exists(),
      "Job sources configured",
      "Missing — copy config/job_sources.yml and add your target companies")

check("config/scoring.yml",
      (_ROOT / "config/scoring.yml").exists(),
      "Scoring rules configured",
      "Missing — copy config/scoring.yml and tune weights/keywords to your domain")


# ── 3. Google Docs / Drive ────────────────────────────────────────────────────

section("3 / 7   Google Docs + Drive (resume reading + creation)")

def _test_gdocs():
    try:
        sys.path.insert(0, str(_ROOT))
        from integrations.google_docs import _load_creds, _read_doc_via_api, _RESUME_DOC_ID
        creds = _load_creds()
        if creds is None:
            return False, "No valid credentials found (need OAuth token or service account)"
        text = _read_doc_via_api(creds)
        if text:
            return True, f"Resume read via Docs API ({len(text)} chars)"
        return False, "Docs API returned empty — check if service account has Editor access on the base resume"
    except Exception as e:
        return False, str(e)

ok, note = _test_gdocs()
check("Read base resume via Docs API", ok, note, note)

def _test_drive():
    try:
        from integrations.google_docs import _load_creds
        from googleapiclient.discovery import build
        creds = _load_creds()
        if creds is None:
            return False, "No credentials"
        drive = build("drive", "v3", credentials=creds)
        folder_id = env("GOOGLE_DRIVE_FOLDER_ID")
        if folder_id:
            drive.files().get(fileId=folder_id, fields="id,name").execute()
            return True, f"Drive folder accessible"
        return True, "Drive API connected (no folder ID set — GDocs will go to root)"
    except Exception as e:
        return False, str(e)

ok, note = _test_drive()
check("Google Drive folder accessible", ok, note, note)


# ── 4. Google Sheets ──────────────────────────────────────────────────────────

section("4 / 7   Google Sheets (job tracking)")

def _test_sheets():
    try:
        from integrations.google_sheets import SheetsClient
        client = SheetsClient()
        if not client._enabled:
            return False, "SheetsClient disabled — check GOOGLE_SHEETS_ID and service account"
        svc = client._get_service()
        meta = svc.spreadsheets().get(spreadsheetId=client._sheet_id).execute()
        tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
        return True, f"Connected — tabs: {', '.join(tabs) or '(none yet)'}"
    except Exception as e:
        return False, str(e)

ok, note = _test_sheets()
check("Google Sheets connected", ok, note, note)


# ── 5. Claude AI ──────────────────────────────────────────────────────────────

section("5 / 7   Claude AI (scoring + resume tailoring)")

def _test_claude():
    try:
        from core.claude_client import _claude_call, is_claude_available, SCORING_MODEL
        if not is_claude_available():
            return False, "claude CLI not on PATH — install Claude Code, then run `claude` to log in"
        r = _claude_call("Return only valid JSON.", 'Reply with exactly: {"status": "OK"}', max_retries=1)
        return True, f"Model responding ({SCORING_MODEL}): {r}"
    except Exception as e:
        return False, f"{e} — if auth error, run `claude` in a terminal and log in"

ok, note = _test_claude()
check("Claude (subscription via claude CLI)", ok, note, note)


# ── 6. Apify ─────────────────────────────────────────────────────────────────

section("6 / 7   Apify (LinkedIn + Indeed scraping)")

def _test_apify():
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.apify.com/v2/users/me",
            headers={"Authorization": f"Bearer {env('APIFY_API_KEY')}"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            username = data.get("data", {}).get("username", "unknown")
            plan = data.get("data", {}).get("plan", {}).get("id", "unknown")
            return True, f"Logged in as @{username} (plan: {plan})"
    except Exception as e:
        return False, str(e)

ok, note = _test_apify()
check("Apify API key valid", ok, note, note)


# ── 7. Notion ─────────────────────────────────────────────────────────────────

section("7 / 7   Notion (optional — P0/P1 database mirroring)")

def _test_notion():
    token = env("NOTION_API_TOKEN")
    if not token:
        return None, "Not configured — Sheets is the primary tracker, Notion is optional"
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.notion.com/v1/users/me",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            name = data.get("name", "unknown")
            return True, f"Logged in as {name}"
    except Exception as e:
        return False, str(e)

result, note = _test_notion()
if result is None:
    print(f"{_WARN}  Notion   — {note}")
    _results.append(("Notion", True, note))  # optional, not a failure
else:
    check("Notion API connected", result, note, note)


# ── Summary ───────────────────────────────────────────────────────────────────

section("Summary")

passed = [r for r in _results if r[1]]
failed = [r for r in _results if not r[1]]

print(f"\n  {len(passed)} / {len(_results)} checks passed\n")

if failed:
    print("  Fix these before running the pipeline:\n")
    for label, _, note in failed:
        print(f"  ✗  {label}")
        if note:
            print(f"       → {note}")
    print()
else:
    print("  Everything is configured. You're ready to run:\n")
    print("    /job-auto-scan          — scout + score + write to Sheets")
    print("    /job-auto-resume-p0     — create GDocs for P0 hot leads")
    print("    /job-auto-resume-p1     — create GDocs for selected P1 jobs")
    print()
    print("  Or run the full pipeline in one shot:")
    print("    python3 orchestrator.py")
    print()
