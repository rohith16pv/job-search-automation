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
from core.dedup import dedup_jobs
from core.filters import apply_hard_filters
from core.scorer import score_jobs_batch
from core.gemini_client import is_gemini_available
from core.resume_tailor import tailor_resume
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
    except Exception:
        return {}


def _save_store(store: dict[str, dict]) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)


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
        Job(**d) for d in store.values()
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
        Job(**d) for d in store.values()
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
    groq = "Groq / Llama 3.1 8B" if is_gemini_available() else "keyword-only"
    print("=" * 60)
    print(f"  Job Search Automation  [{labels.get(mode, mode)}]")
    print(f"  {ts}")
    print(f"  Scoring: {groq}")
    print("=" * 60)


# ── Scouts ────────────────────────────────────────────────────────────────────

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
    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)
        elif isinstance(r, Exception):
            print(f"  Scout error: {r}")
            errors += 1
    print(f"  Raw: {len(all_jobs)} jobs ({errors} scouts errored)")
    return all_jobs


# ── Stage 1: Scan + Assess + Write rows to Sheets ────────────────────────────

async def run_scan_assess() -> None:
    """
    Scout → dedup → filter → score → write P0 + P1 rows to Sheets → save cache.
    GDoc column is left blank — filled by run_resume() in Stage 2.
    """
    _banner("scan")

    print("\n[1/4] Loading resume...")
    resume_text = await read_resume_from_gdoc()

    print("\n[2/4] Scouting all sources...")
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        raw_jobs = await _run_scouts(session)

    print("\n[3/4] Dedup + filter + score...")
    unique = dedup_jobs(raw_jobs, dry_run=False)
    print(f"  {len(unique)} unique (dropped {len(raw_jobs) - len(unique)} dupes)")
    filtered, fstats = apply_hard_filters(unique, max_days=7)
    print(f"  Hard filter: -{fstats['non_usa']} non-USA, -{fstats['stale']} stale → {fstats['kept']} remain")
    scored: list[Job] = await score_jobs_batch(filtered, resume_text)
    scored.sort(key=lambda j: j.score, reverse=True)

    p0 = [j for j in scored if j.score >= 70]
    p1 = [j for j in scored if 50 <= j.score < 70]
    print(f"  P0 (≥70): {len(p0)} | P1 (50-69): {len(p1)} | Dropped: {len(scored)-len(p0)-len(p1)}")

    print("\n[4/4] Writing to Google Sheets...")
    sheets = SheetsClient()

    try:
        notion = NotionClient()
        notion_ok = True
    except Exception as e:
        print(f"  [notion] disabled: {e}")
        notion_ok = False

    for job in p1:
        try:
            if notion_ok:
                notion.add_to_p1(job)
            await sheets.add_row("P1 Jobs", job)
            print(f"  Written to P1 Jobs: {job.company} — {job.title} [{job.score}]")
        except Exception as e:
            print(f"  [write] P1 error ({job.company}): {e}")

    for job in p0:
        try:
            if notion_ok:
                notion.add_to_p0(job)
            await sheets.add_row("P0 Hot Leads", job)  # GDoc URL blank for now
            print(f"  Written to P0 Hot Leads: {job.company} — {job.title} [{job.score}]")
        except Exception as e:
            print(f"  [write] P0 error ({job.company}): {e}")

    # Merge into persistent store (never overwrites existing GDoc URLs)
    _merge_into_store(scored)

    print("\n" + "=" * 60)
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

    print("\n[1/3] Loading resume + pending P0 jobs...")
    resume_text = await read_resume_from_gdoc()
    p0 = _load_pending_p0()  # P0 jobs without a GDoc, across ALL past scans

    if not p0:
        print("  Nothing to do — no jobs with score ≥ 70 in cache.")
        return

    print("\n[2/3] Creating tailored GDocs...")
    sheets = SheetsClient()
    done = 0
    for job in p0:
        try:
            print(f"\n  → {job.title} @ {job.company} [{job.score}]")
            gdoc_url = await tailor_resume(job, resume_text)
            job.resume_gdoc_url = gdoc_url
            _store_update_gdoc(job)  # persist immediately so a crash mid-batch loses nothing
            done += 1
        except Exception as e:
            print(f"  [tailor] error ({job.company}): {e}")

    print("\n[3/3] Updating GDoc URLs in Sheets...")
    for job in p0:
        if job.resume_gdoc_url:
            await sheets.update_gdoc_url(job)

    print("\n" + "=" * 60)
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

    print("\n[1/3] Loading resume + pending P1 jobs...")
    resume_text = await read_resume_from_gdoc()
    p1 = _load_pending_p1()

    if not p1:
        print("  Nothing to do — all P1 jobs already have GDocs, or no P1 jobs in store.")
        return

    print("\n[2/3] Creating tailored GDocs for P1 jobs...")
    sheets = SheetsClient()
    done = 0
    for job in p1:
        try:
            print(f"\n  → {job.title} @ {job.company} [{job.score}]")
            gdoc_url = await tailor_resume(job, resume_text)
            job.resume_gdoc_url = gdoc_url
            _store_update_gdoc(job)  # persist immediately — crash-safe
            done += 1
        except Exception as e:
            print(f"  [tailor] error ({job.company}): {e}")

    print("\n[3/3] Updating GDoc URLs in P1 Jobs sheet...")
    for job in p1:
        if job.resume_gdoc_url:
            try:
                def _do(j=job):
                    svc = sheets._get_service()
                    row = sheets._find_row_by_url(svc, "P1 Jobs", j.url)
                    if row:
                        sheets._update_cell(svc, "P1 Jobs", row, "H", j.resume_gdoc_url)
                        print(f"  [sheets] updated GDoc URL for {j.company} (row {row})")
                    else:
                        print(f"  [sheets] row not found for {j.company} — skipping Sheets update")
                await asyncio.to_thread(_do)
            except Exception as e:
                print(f"  [sheets] update failed ({job.company}): {e}")

    print("\n" + "=" * 60)
    print("  P1 RESUME CREATION COMPLETE")
    print(f"  GDocs created : {done}/{len(p1)}")
    print(f"  Sheets        : https://docs.google.com/spreadsheets/d/{os.environ.get('GOOGLE_SHEETS_ID','')}")
    print("=" * 60)


# ── Full pipeline (original behavior) ────────────────────────────────────────

async def run() -> None:
    _banner("full")

    print("\n[1/6] Loading resume...")
    resume_text = await read_resume_from_gdoc()

    print("\n[2/6] Scouting all sources...")
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        raw_jobs = await _run_scouts(session)

    print("\n[3/6] Dedup + filter...")
    unique = dedup_jobs(raw_jobs, dry_run=DRY_RUN)
    print(f"  {len(unique)} unique (dropped {len(raw_jobs) - len(unique)} dupes)")
    filtered, fstats = apply_hard_filters(unique, max_days=7)
    dropped = fstats["non_usa"] + fstats["stale"]
    if dropped:
        print(f"  Hard filter: -{fstats['non_usa']} non-USA, -{fstats['stale']} stale → {fstats['kept']} remain")

    print("\n[4/6] Scoring...")
    scored: list[Job] = await score_jobs_batch(filtered, resume_text)
    scored.sort(key=lambda j: j.score, reverse=True)

    p0 = [j for j in scored if j.score >= 70]
    p1 = [j for j in scored if 50 <= j.score < 70]

    print(f"\n[5/6] Routing: P0={len(p0)} | P1={len(p1)} | Dropped={len(scored)-len(p0)-len(p1)}")

    if DRY_RUN:
        print("\n--- DRY RUN — top 10 scored jobs ---")
        for job in scored[:10]:
            print(f"  [{job.score:3d}] {job.title} @ {job.company} ({job.source})")
        print("\n[skipped] No writes in dry-run mode.")
        return

    print("\n[6/6] Writing to Notion + Sheets + creating GDocs...")
    try:
        notion = NotionClient()
        notion_ok = True
    except Exception as e:
        print(f"  [notion] disabled: {e}")
        notion_ok = False
    sheets = SheetsClient()

    for job in p1:
        try:
            if notion_ok:
                notion.add_to_p1(job)
            await sheets.add_row("P1 Jobs", job)
        except Exception as e:
            print(f"  [write] P1 error ({job.company}): {e}")

    for job in p0:
        try:
            print(f"\n  Tailoring: {job.title} @ {job.company}...")
            gdoc = await tailor_resume(job, resume_text)
            job.resume_gdoc_url = gdoc
            if notion_ok:
                notion.add_to_p0(job)
            await sheets.add_row("P0 Hot Leads", job)
        except Exception as e:
            print(f"  [write] P0 error ({job.company}): {e}")

    print("\n" + "=" * 60)
    print("  DONE")
    print(f"  P0 (with GDocs) : {len(p0)}")
    print(f"  P1 backlog      : {len(p1)}")
    print("=" * 60)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if SCAN_ONLY:
        asyncio.run(run_scan_assess())
    elif RESUME_ONLY:
        asyncio.run(run_resume())
    elif RESUME_P1:
        asyncio.run(run_resume_p1())
    else:
        asyncio.run(run())
