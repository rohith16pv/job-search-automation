"""
Job Search Orchestrator
=======================
Runs all 11 scouts in parallel, deduplicates, scores, then routes:
  score ≥ 70  → tailor resume → Notion "Ready to Apply" + GSheets "P0 Hot Leads"
  score 50–69 → Notion "P1 Backlog" + GSheets "P1 Jobs"
  score < 50  → dropped

Run modes:
  python orchestrator.py               # full pipeline end-to-end
  python orchestrator.py --dry-run     # score only, no writes
  python orchestrator.py --scan-only   # scout + score + write rows to Sheets (no GDocs)
  python orchestrator.py --resume-only # load cache → tailor P0 → create GDocs → update Sheets
"""
import asyncio
import dataclasses
import json
import os
import shutil
import sys
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import aiohttp

from agents import (
    scout_greenhouse,
    scout_lever,
    scout_ashby,
    scout_smartrecruiters,
    scout_linkedin,
    scout_indeed,
    scout_wellfound,
    scout_workday,
    scout_google_careers,
    scout_amazon_jobs,
    scout_apple_jobs,
)
from agents.base import Job
from core.dedup import dedup_jobs, mark_seen
from core.filters import apply_hard_filters
from core.scorer import score_jobs_batch
from core.claude_client import require_claude, ClaudeUnavailableError, ClaudeUsageLimitError, SCORING_MODEL, TAILORING_MODEL
from core.resume_tailor import tailor_resume
from core import health, improve
from integrations.google_docs import read_resume_from_gdoc
from integrations.notion_client import NotionClient
from integrations.google_sheets import SheetsClient

_CACHE_DIR  = os.path.join(os.path.dirname(__file__), "data")
_STORE_PATH = os.path.join(_CACHE_DIR, "jobs_store.json")  # persistent, never overwritten

DRY_RUN      = "--dry-run"      in sys.argv
SCAN_ONLY    = "--scan-only"    in sys.argv
RESUME_ONLY  = "--resume-only"  in sys.argv
RESUME_P1    = "--resume-p1"    in sys.argv


# ── Persistent job store ──────────────────────────────────────────────────────
# jobs_store.json accumulates every job ever seen, keyed by job.id.
# On each scan, new jobs are merged in. Existing entries keep their
# resume_gdoc_url so already-processed jobs are never re-tailored.

def _load_store() -> dict[str, dict]:
    """Return {job_id: job_dict} from the persistent store (empty if none)."""
    if not os.path.exists(_STORE_PATH):
        return {}
    try:
        with open(_STORE_PATH) as f:
            return json.load(f)
    except Exception as e:
        # Treating a corrupt store as empty would silently re-tailor every job
        # (and re-spend Claude on all of it) — quarantine and abort instead.
        quarantine = _STORE_PATH + ".corrupt"
        shutil.copy2(_STORE_PATH, quarantine)
        raise RuntimeError(
            f"jobs_store.json is unreadable ({e}) — refusing to continue with an empty "
            f"store. Backed up to {quarantine}; restore or delete it, then re-run."
        ) from e


def _save_store(store: dict[str, dict]) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    tmp = _STORE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(store, f, indent=2)
    os.replace(tmp, _STORE_PATH)  # atomic — a crash mid-write can't truncate the store


def _job_from_store(d: dict) -> Job:
    """Rebuild a Job from a store entry, ignoring bookkeeping keys (e.g.
    sheets_pending) that aren't Job dataclass fields."""
    fields = {f.name for f in dataclasses.fields(Job)}
    return Job(**{k: v for k, v in d.items() if k in fields})


def _merge_into_store(jobs: list[Job]) -> dict[str, dict]:
    """
    Merge newly scored jobs into the persistent store.
    - New jobs are added.
    - Existing jobs get score/breakdown updated.
    - resume_gdoc_url is NEVER overwritten if already set (preserves prior work).
    Returns the updated store.
    """
    store = _load_store()
    new_count = 0
    for job in jobs:
        jd = dataclasses.asdict(job)
        if job.id in store:
            existing_gdoc = store[job.id].get("resume_gdoc_url", "")
            store[job.id].update(jd)
            if existing_gdoc:
                store[job.id]["resume_gdoc_url"] = existing_gdoc  # preserve
        else:
            store[job.id] = jd
            new_count += 1
    _save_store(store)
    print(f"  Store: {new_count} new jobs added, {len(store)} total accumulated")
    return store


def _store_update_gdoc(job: Job) -> None:
    """Write GDoc URL back to the persistent store after resume creation."""
    store = _load_store()
    if job.id in store:
        store[job.id]["resume_gdoc_url"] = job.resume_gdoc_url
        _save_store(store)


def _store_flag_sheets_pending(job: Job, pending: bool = True) -> None:
    """Mark a job whose Sheets row failed to publish — retried by
    _sync_pending_sheets() at the start of every subsequent run."""
    store = _load_store()
    if job.id in store:
        if pending:
            store[job.id]["sheets_pending"] = True
        else:
            store[job.id].pop("sheets_pending", None)
        _save_store(store)


def _sheet_tab_for(job: Job) -> str:
    return "P0 Hot Leads" if job.score >= 70 else ("P1 Jobs" if job.score >= 50 else "P2 Review")


async def _sync_pending_sheets(sheets) -> None:
    """Retry Sheets rows that failed to publish in earlier runs. The store is
    the source of truth; this heals the 'GDoc exists but Sheets row is stale'
    gap left by transient Sheets failures."""
    store = _load_store()
    pending = [(jid, d) for jid, d in store.items() if d.get("sheets_pending")]
    if not pending:
        return
    print(f"  [sheets] retrying {len(pending)} row(s) that failed to publish previously...")
    cleared = []
    for jid, d in pending:
        job = _job_from_store(d)
        tab = _sheet_tab_for(job)
        if job.resume_gdoc_url:
            ok = await sheets.update_gdoc_url(job, tab)  # upserts the GDoc link
        else:
            ok = await sheets.upsert_row(tab, job)  # appends only if the row is missing
        if ok:
            cleared.append(jid)
        else:
            print(f"  [sheets] ⚠ still failing for {job.company} — will retry next run")
    if cleared:
        store = _load_store()
        for jid in cleared:
            store.get(jid, {}).pop("sheets_pending", None)
        _save_store(store)


def _load_pending_p0() -> list[Job]:
    """
    Return all P0 jobs (score ≥ 70) that don't yet have a GDoc URL.
    Spans all previous scans — nothing is lost across runs.
    """
    store = _load_store()
    if not store:
        raise FileNotFoundError(
            "No job store found. Run `python orchestrator.py --scan-only` first."
        )
    pending = [
        _job_from_store(d) for d in store.values()
        if d.get("score", 0) >= 70 and not d.get("resume_gdoc_url", "")
    ]
    total_p0 = sum(1 for d in store.values() if d.get("score", 0) >= 70)
    done = total_p0 - len(pending)
    print(f"  Store: {len(store)} total jobs | P0 (≥70): {total_p0} | already done: {done} | pending: {len(pending)}")
    return pending


def _load_pending_p1() -> list[Job]:
    """
    Return all P1 jobs (score 50–69) that don't yet have a GDoc URL.
    Spans all previous scans — nothing is lost across runs.
    """
    store = _load_store()
    if not store:
        raise FileNotFoundError(
            "No job store found. Run `python orchestrator.py --scan-only` first."
        )
    pending = [
        _job_from_store(d) for d in store.values()
        if 50 <= d.get("score", 0) < 70 and not d.get("resume_gdoc_url", "")
    ]
    total_p1 = sum(1 for d in store.values() if 50 <= d.get("score", 0) < 70)
    done = total_p1 - len(pending)
    print(f"  Store: {len(store)} total jobs | P1 (50-69): {total_p1} | already done: {done} | pending: {len(pending)}")
    return pending


# ── Banner ────────────────────────────────────────────────────────────────────

def _banner(mode: str = "full") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M %Z")
    labels = {
        "full":      "Full Pipeline",
        "scan":      "Stage 1 — Scan + Assess + Write Sheets",
        "resume":    "Stage 2a — Create P0 Tailored Resumes",
        "resume-p1": "Stage 2b — Create P1 Tailored Resumes",
        "dry":       "Dry Run — Score Only",
    }
    print("=" * 60)
    print(f"  Job Search Automation  [{labels.get(mode, mode)}]")
    print(f"  {ts}")
    print(f"  Models: scoring {SCORING_MODEL} | tailoring {TAILORING_MODEL} (subscription via claude CLI)")
    print("=" * 60)
    require_claude()  # Claude is mandatory — fail here, before any scraping


# ── Scouts ────────────────────────────────────────────────────────────────────

_SCOUT_NAMES = [
    "greenhouse", "lever", "ashby", "smartrecruiters",
    "wellfound", "workday", "google_careers", "amazon_jobs", "apple_jobs",
    "linkedin", "indeed",
]

# Sources that historically return 0 on normal days are expected-zero; all others
# should return >0 or we surface a loud warning.
_EXPECTED_ZERO_OK = set()  # none — every source should occasionally find something

# If total raw jobs across all sources is below this, something is systemically
# broken and we abort rather than waste Claude usage scoring nothing.
_MIN_RAW_JOBS = 10


async def _run_scouts(session: aiohttp.ClientSession) -> list[Job]:
    print("\n[scouts] Firing all 11 scouts in parallel...")
    session_scouts = [
        scout_greenhouse(session),
        scout_lever(session),
        scout_ashby(session),
        scout_smartrecruiters(session),
        scout_wellfound(session),
        scout_workday(session),
        scout_google_careers(session),
        scout_amazon_jobs(session),
        scout_apple_jobs(session),
    ]
    thread_scouts = [
        asyncio.to_thread(scout_linkedin),
        asyncio.to_thread(scout_indeed),
    ]
    results = await asyncio.gather(*session_scouts, *thread_scouts, return_exceptions=True)

    all_jobs: list[Job] = []
    errors = 0
    warnings = 0

    print("\n  ┌─────────────────────────────┬────────┬────────┐")
    print("  │ Source                      │  Jobs  │ Status │")
    print("  ├─────────────────────────────┼────────┼────────┤")

    for name, r in zip(_SCOUT_NAMES, results):
        if isinstance(r, Exception):
            status = "ERROR "
            count = 0
            errors += 1
            print(f"  │ {name:<27} │ {'—':>6} │ {status} │")
            print(f"  │   ↳ {str(r)[:65]}")
        elif isinstance(r, list):
            count = len(r)
            all_jobs.extend(r)
            if count == 0 and name not in _EXPECTED_ZERO_OK:
                status = "WARN  "
                warnings += 1
            else:
                status = "OK    "
            print(f"  │ {name:<27} │ {count:>6} │ {status} │")
        else:
            status = "ERROR "
            errors += 1
            print(f"  │ {name:<27} │ {'—':>6} │ {status} │")

    print("  ├─────────────────────────────┼────────┼────────┤")
    print(f"  │ {'TOTAL':<27} │ {len(all_jobs):>6} │        │")
    print("  └─────────────────────────────┴────────┴────────┘")

    if errors:
        print(f"\n  ⚠  {errors} scout(s) threw exceptions — check logs above.")
    if warnings:
        print(f"  ⚠  {warnings} scout(s) returned 0 jobs — actor may be broken or misconfigured.")

    if len(all_jobs) < _MIN_RAW_JOBS:
        raise RuntimeError(
            f"Sanity check failed: only {len(all_jobs)} raw jobs found across all sources "
            f"(threshold: {_MIN_RAW_JOBS}). Aborting before scoring to avoid wasting API credits. "
            "Check scout errors above."
        )

    return all_jobs


# ── Stage 1: Scan + Assess + Write rows to Sheets ────────────────────────────

async def run_scan_assess() -> None:
    """
    Scout → dedup → filter → score → write P0 + P1 rows to Sheets → save cache.
    GDoc column is left blank — filled by run_resume() in Stage 2.
    """
    _banner("scan")

    health.preflight()  # Claude / Sheets / Apify / last-run gap — fail before spending

    print("\n[1/4] Loading resume...")
    resume_text = await read_resume_from_gdoc()

    print("\n[2/4] Scouting all sources...")
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        raw_jobs = await _run_scouts(session)
        await health.audit_ats_slugs(session)  # flag boards that stopped resolving

    from collections import Counter
    health.record_and_check_counts(dict(Counter(j.source for j in raw_jobs)))

    print("\n[3/4] Dedup + filter + score...")
    unique = dedup_jobs(raw_jobs)  # detection only — marked seen after writes succeed
    print(f"  {len(unique)} unique (dropped {len(raw_jobs) - len(unique)} dupes)")
    filtered, fstats = apply_hard_filters(unique, max_days=20)
    print(f"  Hard filter: -{fstats['non_usa']} non-USA, -{fstats['stale']} stale → {fstats['kept']} remain")
    limit_hit = False
    try:
        scored: list[Job] = await score_jobs_batch(filtered, resume_text)
    except ClaudeUsageLimitError as e:
        # Publish the scores already paid for; unscored jobs are NOT marked
        # seen, so the next run rescans and rescores them.
        scored = getattr(e, "scored", []) or []
        if not scored:
            raise
        limit_hit = True
        print(f"\n  ⚠ {e}")
        print(f"  Publishing {len(scored)} already-scored job(s); the rest will be rescored next run.")
    scored.sort(key=lambda j: j.score, reverse=True)

    p0 = [j for j in scored if j.score >= 70]
    p1 = [j for j in scored if 50 <= j.score < 70]
    p2 = [j for j in scored if 40 <= j.score < 50]
    print(f"  P0 (≥70): {len(p0)} | P1 (50-69): {len(p1)} | P2 (40-49): {len(p2)} | Dropped: {len(scored)-len(p0)-len(p1)-len(p2)}")

    print("\n[4/4] Writing to Google Sheets...")
    # Persist BEFORE the writes so a failed Sheets row can be flagged for retry
    # (never overwrites existing GDoc URLs)
    _merge_into_store(scored)
    sheets = SheetsClient()
    await _sync_pending_sheets(sheets)  # heal rows that failed in earlier runs

    try:
        notion = NotionClient()
        notion_ok = True
    except Exception as e:
        print(f"  [notion] disabled: {e}")
        notion_ok = False

    def _notion_write(fn, job):
        try:
            fn(job)
        except Exception as e:
            print(f"  [notion] write error ({job.company}): {e}")

    # Sheets first (primary tracker), Notion second — a Notion failure must
    # never block the Sheets row. Failed rows are flagged for next-run retry.
    for job in p1:
        if await sheets.add_row("P1 Jobs", job):
            print(f"  Written to P1 Jobs: {job.company} — {job.title} [{job.score}]")
        else:
            _store_flag_sheets_pending(job)
        if notion_ok:
            _notion_write(notion.add_to_p1, job)

    for job in p0:
        if await sheets.add_row("P0 Hot Leads", job):  # GDoc URL blank for now
            print(f"  Written to P0 Hot Leads: {job.company} — {job.title} [{job.score}]")
        else:
            _store_flag_sheets_pending(job)
        if notion_ok:
            _notion_write(notion.add_to_p0, job)

    for job in p2:
        if not await sheets.add_row("P2 Review", job):
            _store_flag_sheets_pending(job)
    if p2:
        print(f"  Written {len(p2)} borderline jobs to 'P2 Review' tab")

    # Only now — after scoring and writes completed — mark the batch as seen.
    # On a usage-limit partial, mark only the scored jobs: unscored ones must
    # come back next run.
    mark_seen(scored if limit_hit else unique)
    health.mark_run_complete({"raw": len(raw_jobs), "scored": len(scored), "p0": len(p0), "p1": len(p1)})

    # Self-improvement: auto-add ATS boards for untracked companies that
    # produced relevant search hits, and (Sundays) run the Claude self-review.
    additions = await asyncio.to_thread(improve.discover_boards, scored)
    if additions:
        print(f"  [improve] {len(additions)} new company board(s) added to config: {', '.join(additions)}")
    await asyncio.to_thread(improve.weekly_review)

    print("\n" + "=" * 60)
    if limit_hit:
        print("  SCAN + ASSESS PARTIAL — CLAUDE USAGE LIMIT REACHED")
        print(f"  Scored + published {len(scored)} job(s); unscored jobs will be rescored next run.")
    else:
        print("  SCAN + ASSESS COMPLETE")
    print(f"  P0 Hot Leads : {len(p0)} roles (GDoc column blank — run /job-auto-resume next)")
    print(f"  P1 Backlog   : {len(p1)} roles")
    print(f"  Sheets       : https://docs.google.com/spreadsheets/d/{os.environ.get('GOOGLE_SHEETS_ID','')}")
    print("=" * 60)


# ── Stage 2: Tailor resumes + update GDoc URLs in Sheets ─────────────────────

async def run_resume() -> None:
    """
    Load P0 jobs from cache → tailor each → create GDoc → update Sheets row with GDoc URL.
    """
    _banner("resume")

    print("\n[1/2] Loading resume + pending P0 jobs...")
    resume_text = await read_resume_from_gdoc()
    p0 = _load_pending_p0()  # P0 jobs without a GDoc, across ALL past scans

    if not p0:
        print("  Nothing to do — no jobs with score ≥ 70 in cache.")
        return

    print("\n[2/2] Creating tailored GDocs + updating Sheets...")
    sheets = SheetsClient()
    await _sync_pending_sheets(sheets)  # heal rows that failed in earlier runs
    done = 0
    limit_hit = False
    for job in p0:
        try:
            print(f"\n  → {job.title} @ {job.company} [{job.score}]")
            gdoc_url = await tailor_resume(job, resume_text)
            job.resume_gdoc_url = gdoc_url
            _store_update_gdoc(job)  # persist immediately so a crash mid-batch loses nothing
            if not await sheets.update_gdoc_url(job):  # publish immediately — Sheets never lags the store
                _store_flag_sheets_pending(job)  # retried automatically next run
            done += 1
        except ClaudeUnavailableError:
            raise  # systemic — abort the whole run, don't churn through remaining jobs
        except ClaudeUsageLimitError as e:
            limit_hit = True
            print(f"\n  ⚠ {e}")
            break  # stop spending — completed GDocs are already in Sheets
        except Exception as e:
            print(f"  [tailor] error ({job.company}): {e}")

    print("\n" + "=" * 60)
    if limit_hit:
        print("  RESUME CREATION PAUSED — CLAUDE USAGE LIMIT REACHED")
        print(f"  GDocs created : {done}/{len(p0)} (already published to Sheets)")
        print(f"  Remaining     : {len(p0) - done} — re-run /job-auto-resume-p0 after the limit resets")
    else:
        print("  RESUME CREATION COMPLETE")
        print(f"  GDocs created : {done}/{len(p0)}")
    print(f"  Sheets        : https://docs.google.com/spreadsheets/d/{os.environ.get('GOOGLE_SHEETS_ID','')}")
    print("=" * 60)


# ── Stage 2b: Tailor P1 resumes ──────────────────────────────────────────────

async def run_resume_p1() -> None:
    """
    Load P1 jobs (score 50–69) from store → tailor each → create GDoc → update Sheets row.
    Same flow as run_resume() but targets the P1 backlog tab.
    """
    _banner("resume-p1")

    print("\n[1/2] Loading resume + pending P1 jobs...")
    resume_text = await read_resume_from_gdoc()
    p1 = _load_pending_p1()

    if not p1:
        print("  Nothing to do — all P1 jobs already have GDocs, or no P1 jobs in store.")
        return

    print("\n[2/2] Creating tailored GDocs for P1 jobs + updating Sheets...")
    sheets = SheetsClient()
    await _sync_pending_sheets(sheets)  # heal rows that failed in earlier runs
    done = 0
    limit_hit = False
    for job in p1:
        try:
            print(f"\n  → {job.title} @ {job.company} [{job.score}]")
            gdoc_url = await tailor_resume(job, resume_text)
            job.resume_gdoc_url = gdoc_url
            _store_update_gdoc(job)  # persist immediately — crash-safe
            if not await sheets.update_gdoc_url(job, "P1 Jobs"):  # publish immediately — Sheets never lags the store
                _store_flag_sheets_pending(job)  # retried automatically next run
            done += 1
        except ClaudeUnavailableError:
            raise  # systemic — abort the whole run, don't churn through remaining jobs
        except ClaudeUsageLimitError as e:
            limit_hit = True
            print(f"\n  ⚠ {e}")
            break  # stop spending — completed GDocs are already in Sheets
        except Exception as e:
            print(f"  [tailor] error ({job.company}): {e}")

    print("\n" + "=" * 60)
    if limit_hit:
        print("  P1 RESUME CREATION PAUSED — CLAUDE USAGE LIMIT REACHED")
        print(f"  GDocs created : {done}/{len(p1)} (already published to Sheets)")
        print(f"  Remaining     : {len(p1) - done} — re-run /job-auto-resume-p1 after the limit resets")
    else:
        print("  P1 RESUME CREATION COMPLETE")
        print(f"  GDocs created : {done}/{len(p1)}")
    print(f"  Sheets        : https://docs.google.com/spreadsheets/d/{os.environ.get('GOOGLE_SHEETS_ID','')}")
    print("=" * 60)


# ── Full pipeline (original behavior) ────────────────────────────────────────

async def run() -> None:
    _banner("full")

    if not DRY_RUN:
        health.preflight()  # Claude / Sheets / Apify / last-run gap — fail before spending

    print("\n[1/6] Loading resume...")
    resume_text = await read_resume_from_gdoc()

    print("\n[2/6] Scouting all sources...")
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        raw_jobs = await _run_scouts(session)
        await health.audit_ats_slugs(session)

    from collections import Counter
    health.record_and_check_counts(dict(Counter(j.source for j in raw_jobs)))

    print("\n[3/6] Dedup + filter...")
    unique = dedup_jobs(raw_jobs)  # detection only — marked seen after writes succeed
    print(f"  {len(unique)} unique (dropped {len(raw_jobs) - len(unique)} dupes)")
    filtered, fstats = apply_hard_filters(unique, max_days=20)
    dropped = fstats["non_usa"] + fstats["stale"]
    if dropped:
        print(f"  Hard filter: -{fstats['non_usa']} non-USA, -{fstats['stale']} stale → {fstats['kept']} remain")

    print("\n[4/6] Scoring...")
    limit_hit = False
    try:
        scored: list[Job] = await score_jobs_batch(filtered, resume_text)
    except ClaudeUsageLimitError as e:
        # Publish the scores already paid for; unscored jobs are NOT marked
        # seen, so the next run rescans and rescores them. Tailoring is
        # skipped (the limit is already hit) — P0 GDocs come later via
        # /job-auto-resume-p0.
        scored = getattr(e, "scored", []) or []
        if not scored:
            raise
        limit_hit = True
        print(f"\n  ⚠ {e}")
        print(f"  Publishing {len(scored)} already-scored job(s); the rest will be rescored next run.")
    scored.sort(key=lambda j: j.score, reverse=True)

    p0 = [j for j in scored if j.score >= 70]
    p1 = [j for j in scored if 50 <= j.score < 70]
    p2 = [j for j in scored if 40 <= j.score < 50]

    print(f"\n[5/6] Routing: P0={len(p0)} | P1={len(p1)} | P2={len(p2)} | Dropped={len(scored)-len(p0)-len(p1)-len(p2)}")

    if DRY_RUN:
        print("\n--- DRY RUN — top 10 scored jobs ---")
        for job in scored[:10]:
            print(f"  [{job.score:3d}] {job.title} @ {job.company} ({job.source})")
        print("\n[skipped] No writes in dry-run mode.")
        return

    print("\n[6/6] Writing to Notion + Sheets + creating GDocs...")
    # Persist scored jobs BEFORE tailoring: if the usage limit hits mid-batch,
    # untailored P0/P1 jobs stay pending in the store for /job-auto-resume-*.
    _merge_into_store(scored)
    try:
        notion = NotionClient()
        notion_ok = True
    except Exception as e:
        print(f"  [notion] disabled: {e}")
        notion_ok = False
    sheets = SheetsClient()
    await _sync_pending_sheets(sheets)  # heal rows that failed in earlier runs

    def _notion_write(fn, job):
        try:
            fn(job)
        except Exception as e:
            print(f"  [notion] write error ({job.company}): {e}")

    for job in p1:
        if not await sheets.add_row("P1 Jobs", job):
            _store_flag_sheets_pending(job)
        if notion_ok:
            _notion_write(notion.add_to_p1, job)

    for job in p0:
        if not limit_hit:
            try:
                print(f"\n  Tailoring: {job.title} @ {job.company}...")
                gdoc = await tailor_resume(job, resume_text)
                job.resume_gdoc_url = gdoc
                _store_update_gdoc(job)  # persist immediately — crash-safe
            except ClaudeUnavailableError:
                raise
            except ClaudeUsageLimitError as e:
                limit_hit = True
                print(f"\n  ⚠ {e}")
                print("  Remaining P0 jobs stay pending in the store — run /job-auto-resume-p0 after the limit resets.")
            except Exception as e:
                print(f"  [tailor] error ({job.company}): {e}")
        # Publish the row regardless — Sheets first (primary tracker), then
        # Notion. A tailoring or Notion failure must never bury a hot lead.
        if not await sheets.add_row("P0 Hot Leads", job):
            _store_flag_sheets_pending(job)
        if notion_ok:
            _notion_write(notion.add_to_p0, job)

    for job in p2:
        if not await sheets.add_row("P2 Review", job):
            _store_flag_sheets_pending(job)

    # Only now — after scoring and writes completed — mark the batch as seen.
    # On a usage-limit partial, mark only the scored jobs: unscored ones must
    # come back next run.
    mark_seen(scored if limit_hit else unique)
    health.mark_run_complete({"raw": len(raw_jobs), "scored": len(scored), "p0": len(p0), "p1": len(p1)})

    additions = await asyncio.to_thread(improve.discover_boards, scored)
    if additions:
        print(f"  [improve] {len(additions)} new company board(s) added to config: {', '.join(additions)}")
    await asyncio.to_thread(improve.weekly_review)

    print("\n" + "=" * 60)
    if limit_hit:
        tailored = sum(1 for j in p0 if j.resume_gdoc_url)
        print("  DONE (PAUSED EARLY — CLAUDE USAGE LIMIT REACHED)")
        print(f"  P0 (with GDocs) : {tailored}/{len(p0)} — rest pending; /job-auto-resume-p0 after reset")
    else:
        print("  DONE")
        print(f"  P0 (with GDocs) : {len(p0)}")
    print(f"  P1 backlog      : {len(p1)}")
    print("=" * 60)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        if SCAN_ONLY:
            asyncio.run(run_scan_assess())
        elif RESUME_ONLY:
            asyncio.run(run_resume())
        elif RESUME_P1:
            asyncio.run(run_resume_p1())
        else:
            asyncio.run(run())
    except ClaudeUnavailableError as e:
        print("\n" + "!" * 60)
        print("  RUN ABORTED — CLAUDE UNAVAILABLE")
        print(f"  {e}")
        print("!" * 60)
        raise SystemExit(1)
    except ClaudeUsageLimitError as e:
        # Reached here only when the limit hits during SCORING (tailoring loops
        # handle it inline). Nothing was written yet and nothing is marked seen,
        # so the next run rescans and rescores the same batch cleanly.
        print("\n" + "!" * 60)
        print("  RUN STOPPED — CLAUDE USAGE LIMIT REACHED")
        print(f"  {e}")
        print("!" * 60)
        raise SystemExit(2)
