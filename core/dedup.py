"""
Deduplication — filters jobs already seen in prior runs.
State is stored in data/seen_jobs.jsonl (one job ID per line).
"""
import json
import os
from agents.base import Job

_SEEN_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "seen_jobs.jsonl")


def _load_seen() -> set[str]:
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


def _save_new(jobs: list[Job]) -> None:
    os.makedirs(os.path.dirname(_SEEN_PATH), exist_ok=True)
    with open(_SEEN_PATH, "a") as f:
        for job in jobs:
            f.write(json.dumps({"id": job.id, "url": job.url, "title": job.title, "company": job.company}) + "\n")


def dedup_jobs(jobs: list[Job], dry_run: bool = False) -> list[Job]:
    """
    Returns only jobs not seen in previous runs.
    Also deduplicates within the current batch by URL.
    Persists new job IDs to the seen file (skipped in dry_run mode).
    """
    seen_ids = _load_seen()

    batch_seen: set[str] = set()
    unique: list[Job] = []
    for job in jobs:
        if job.id not in seen_ids and job.id not in batch_seen:
            unique.append(job)
            batch_seen.add(job.id)

    if not dry_run:
        _save_new(unique)
    return unique
