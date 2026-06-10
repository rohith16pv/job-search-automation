"""
Deduplication — filters jobs already seen in prior runs.
State is stored in data/seen_jobs.jsonl (one job ID per line).

IMPORTANT: detection and persistence are split. `dedup_jobs()` only detects;
the orchestrator calls `mark_seen()` AFTER scoring and writes succeed. This
way a run that aborts mid-way (Claude auth, crash) does not permanently bury
jobs that were fetched but never processed — they simply return next run.
"""
import json
import os
from agents.base import Job

_SEEN_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "seen_jobs.jsonl")


def _load_seen() -> set:
    seen = set()
    if not os.path.exists(_SEEN_PATH):
        return seen
    with open(_SEEN_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    seen.add(json.loads(line)["id"])
                except Exception:
                    pass
    return seen


def dedup_jobs(jobs: list) -> list:
    """
    Returns only jobs not seen in previous runs (detection only — does NOT
    persist anything). Also deduplicates within the current batch by ID.
    """
    seen_ids = _load_seen()
    batch_seen = set()
    unique = []
    for job in jobs:
        if job.id not in seen_ids and job.id not in batch_seen:
            unique.append(job)
            batch_seen.add(job.id)
    return unique


def mark_seen(jobs: list) -> None:
    """Persist job IDs as seen. Call ONLY after the batch has been fully
    processed (scored + written) — never before."""
    if not jobs:
        return
    seen_ids = _load_seen()
    os.makedirs(os.path.dirname(_SEEN_PATH), exist_ok=True)
    with open(_SEEN_PATH, "a") as f:
        for job in jobs:
            if job.id in seen_ids:
                continue
            f.write(json.dumps({
                "id": job.id, "url": job.url, "title": job.title, "company": job.company,
            }) + "\n")
            seen_ids.add(job.id)
