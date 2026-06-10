"""
Daily sanity checks — every scan runs these so a silently broken source can
never cost more than one day of postings.

  preflight()                  — Claude ping, Sheets reachable, Apify key,
                                 gap-since-last-run warning. Fatal on Claude
                                 or Sheets failure (fail BEFORE spending).
  record_and_check_counts()    — per-source job counts vs trailing baseline;
                                 flags zeros and >60% drops (slug rot / API
                                 changes show up here the day they happen).
  audit_ats_slugs()            — probes every Greenhouse/Lever/Ashby slug;
                                 flags boards that stopped resolving.
  mark_run_complete()          — records the last successful scan timestamp
                                 (read by the scheduler's catch-up logic).

History lives in data/health_history.json (last 60 runs).
"""
import asyncio
import json
import os
import statistics
from datetime import datetime

import aiohttp

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_HIST_PATH = os.path.join(_DATA_DIR, "health_history.json")
_LAST_RUN_PATH = os.path.join(_DATA_DIR, "last_run.json")

# Scouts that are known-degraded (client-side rendering / anti-bot) — a zero
# from these is expected and must not page the user every day.
KNOWN_DEGRADED = {"apple_jobs", "wellfound"}

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ── Pre-flight ────────────────────────────────────────────────────────────────

def preflight() -> None:
    """Verify every critical dependency BEFORE scraping or spending Claude
    usage. Claude and Sheets failures abort; the rest warn loudly."""
    print("\n[health] Pre-flight checks...")

    # 1. Claude — CLI present AND authenticated (tiny live ping)
    from core.claude_client import require_claude, _claude_call, ClaudeUnavailableError, ClaudeUsageLimitError
    require_claude()
    try:
        _claude_call("Health check. Return only valid JSON.", 'Reply with exactly: {"ok": true}',
                     max_retries=1)
        print("  ✓ Claude reachable (subscription auth OK)")
    except (ClaudeUnavailableError, ClaudeUsageLimitError):
        # A usage limit must surface as itself (exit code 2, "wait for reset"),
        # never as ClaudeUnavailableError (exit code 1, "log in again").
        raise
    except Exception as e:
        raise ClaudeUnavailableError(f"Claude health ping failed: {e}")

    # 2. Google Sheets — creds valid and spreadsheet reachable
    from integrations.google_sheets import SheetsClient
    sheets = SheetsClient()
    if not sheets._enabled:
        raise RuntimeError(
            "Google Sheets not configured (GOOGLE_SHEETS_ID / service account) — "
            "aborting before scraping so no postings get buried."
        )
    try:
        sheets._get_service().spreadsheets().get(spreadsheetId=sheets._sheet_id).execute()
        print("  ✓ Google Sheets reachable")
    except Exception as e:
        raise RuntimeError(f"Google Sheets unreachable ({e}) — aborting before scraping.")

    # 3. Apify — warn only (LinkedIn + Indeed silently skip without it)
    if os.environ.get("APIFY_API_KEY"):
        print("  ✓ Apify key set (LinkedIn + Indeed active)")
    else:
        print("  ⚠ APIFY_API_KEY missing — LinkedIn and Indeed scouts will be SKIPPED")

    # 4. Gap since last successful scan
    last = _load_json(_LAST_RUN_PATH, {})
    if last.get("completed_at"):
        try:
            gap_h = (datetime.now() - datetime.fromisoformat(last["completed_at"])).total_seconds() / 3600
            if gap_h > 26:
                print(f"  ⚠ Last successful scan was {gap_h:.0f}h ago — source windows (7-day) "
                      f"cover the gap, but check the scheduler if this recurs")
            else:
                print(f"  ✓ Last successful scan {gap_h:.0f}h ago")
        except Exception:
            pass
    else:
        print("  • No prior run recorded (first scan with health tracking)")


# ── Per-source count baselines ───────────────────────────────────────────────

def record_and_check_counts(counts: dict) -> list:
    """Compare today's per-source counts to the trailing median; persist the
    run. Returns warning strings (also printed)."""
    hist = _load_json(_HIST_PATH, [])
    warnings = []

    baselines = {}
    for run in hist[-7:]:
        for src, n in run.get("counts", {}).items():
            baselines.setdefault(src, []).append(n)

    # Sources that disappeared entirely from this run's counts
    expected = set(baselines) | set(counts)
    for src in sorted(expected):
        n = counts.get(src, 0)
        base = statistics.median(baselines[src]) if baselines.get(src) else None
        if n == 0 and src not in KNOWN_DEGRADED:
            note = f" (baseline ~{base:.0f})" if base else ""
            warnings.append(f"{src} returned 0 jobs{note} — endpoint, slugs, or API may have broken")
        elif base and base >= 5 and n < base * 0.4:
            warnings.append(f"{src} returned {n} jobs vs baseline ~{base:.0f} — possible partial breakage")

    if warnings:
        print("\n  ⚠ SCOUT HEALTH WARNINGS:")
        for w in warnings:
            print(f"    - {w}")

    hist.append({"date": datetime.now().isoformat(timespec="seconds"), "counts": counts})
    _save_json(_HIST_PATH, hist[-60:])
    return warnings


# ── ATS slug audit ────────────────────────────────────────────────────────────

async def _probe(session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore) -> bool:
    # Semaphore caps concurrency to avoid tripping ATS rate limits.
    # (Created per-call — a module-level Semaphore binds the wrong loop on py3.9.)
    async with sem:
        try:
            async with session.get(url, headers=_UA, timeout=aiohttp.ClientTimeout(total=12)) as r:
                # 429 = rate-limited, not dead — never flag those
                return r.status == 200 or r.status == 429
        except Exception:
            return True  # network blips are not "board is dead" evidence


async def audit_ats_slugs(session: aiohttp.ClientSession) -> list:
    """Probe every configured Greenhouse/Lever/Ashby board. Returns warnings
    for boards that no longer resolve (companies move ATS without notice)."""
    import yaml
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    probes = []
    for slug in cfg.get("greenhouse", []):
        probes.append(("greenhouse", slug, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"))
    for slug in cfg.get("lever", []):
        probes.append(("lever", slug, f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=1"))
    for slug in cfg.get("ashby", []):
        probes.append(("ashby", slug, f"https://api.ashbyhq.com/posting-api/job-board/{slug}"))

    sem = asyncio.Semaphore(10)
    results = await asyncio.gather(*[_probe(session, url, sem) for _, _, url in probes])
    dead = [(ats, slug) for (ats, slug, _), ok in zip(probes, results) if not ok]

    warnings = [f"{ats}/{slug} board no longer resolves — company may have moved ATS" for ats, slug in dead]
    if warnings:
        print("\n  ⚠ DEAD ATS BOARDS:")
        for w in warnings:
            print(f"    - {w}")
    else:
        print(f"  ✓ All {len(probes)} configured ATS boards resolve")
    return warnings


# ── Run completion marker ────────────────────────────────────────────────────

def mark_run_complete(stats: dict = None) -> None:
    _save_json(_LAST_RUN_PATH, {
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        **(stats or {}),
    })


def hours_since_last_run() -> float:
    """Used by the scheduler's catch-up logic. Returns inf if never run."""
    last = _load_json(_LAST_RUN_PATH, {})
    if not last.get("completed_at"):
        return float("inf")
    try:
        return (datetime.now() - datetime.fromisoformat(last["completed_at"])).total_seconds() / 3600
    except Exception:
        return float("inf")
