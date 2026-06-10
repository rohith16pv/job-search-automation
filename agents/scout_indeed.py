"""
Indeed scout — uses Apify's Indeed scraper actor.
Requires APIFY_API_KEY in .env. Skipped gracefully if key is missing.
All queries fire in parallel via ThreadPoolExecutor.
"""
import os
import re
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from .base import Job, make_job_id


def _ago_to_iso(posted: str) -> str:
    """Normalize Indeed's 'Just posted' / 'Today' / 'N days ago' to ISO."""
    p = (posted or "").lower()
    if not p:
        return ""
    if "just" in p or "today" in p:
        return str(date.today())
    m = re.search(r"(\d+)\+?\s*day", p)
    if m:
        return str(date.today() - timedelta(days=int(m.group(1))))
    return posted


def _load_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
    with open(cfg_path) as f:
        return yaml.safe_load(f).get("indeed", {})


def _run_query(api_key: str, query: str) -> list[Job]:
    from apify_client import ApifyClient
    client = ApifyClient(api_key)
    run_input = {
        "position": query,
        "country": "US",
        "maxItemsPerSearch": 50,
        "saveOnlyUniqueItems": True,
    }
    # timeout_secs aborts a hung actor run server-side; wait_secs caps how long
    # we block client-side — one stuck source must never stall the whole pipeline.
    run = client.actor("misceres/indeed-scraper").call(
        run_input=run_input, timeout_secs=300, wait_secs=330
    )
    status = (run or {}).get("status", "")
    if status != "SUCCEEDED":
        print(f"  [indeed] WARNING: query '{query}' actor run ended "
              f"'{status or 'UNKNOWN'}' (timeout 300s) — skipping this query")
        return []
    dataset_id = run.get("defaultDatasetId", "")
    if not dataset_id:
        return []
    jobs = []
    for item in client.dataset(dataset_id).iterate_items():
        job_url = item.get("url", item.get("jobUrl", ""))
        if not job_url:
            continue
        jobs.append(Job(
            id=make_job_id(job_url),
            title=item.get("positionName", item.get("title", "")),
            company=item.get("company", ""),
            url=job_url,
            description=item.get("description", ""),
            location=item.get("location", ""),
            source="indeed",
            posted_date=_ago_to_iso(item.get("postedAt", "")),
            salary_min=item.get("salaryMin", 0) or 0,
            salary_max=item.get("salaryMax", 0) or 0,
        ))
    return jobs


def scout_indeed() -> list[Job]:
    api_key = os.environ.get("APIFY_API_KEY", "")
    if not api_key:
        print("  [indeed] skipped — no APIFY_API_KEY")
        return []

    try:
        from apify_client import ApifyClient  # noqa: F401
    except ImportError:
        print("  [indeed] skipped — apify-client not installed")
        return []

    cfg = _load_config()
    queries = cfg.get("queries", ["Senior Product Manager payments"])

    all_jobs: list[Job] = []
    # Fire all queries in parallel — wall-clock = slowest single query, not sum
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        futures = {pool.submit(_run_query, api_key, q): q for q in queries}
        for future in as_completed(futures):
            query = futures[future]
            try:
                all_jobs.extend(future.result())
            except Exception as e:
                print(f"  [indeed] query '{query}': {e}")

    print(f"  [indeed] {len(all_jobs)} jobs")
    return all_jobs
