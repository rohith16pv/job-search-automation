"""
LinkedIn Jobs scout — uses Apify's LinkedIn Jobs Scraper actor.
Requires APIFY_API_KEY in .env. Skipped gracefully if key is missing.
All queries fire in parallel via ThreadPoolExecutor.
"""
import os
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from .base import Job, make_job_id


def _load_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
    with open(cfg_path) as f:
        return yaml.safe_load(f).get("linkedin", {})


def _run_query(client, query: str, location: str, time_filter: str) -> list[Job]:
    search_url = (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={query.replace(' ', '%20')}"
        f"&location={location.replace(' ', '%20')}"
        f"&f_TPR={time_filter}"
        f"&f_WT=2"  # Remote
    )
    run_input = {
        "urls": [search_url],
        "count": 50,
        "scrapeCompany": False,
    }
    run = client.actor("hKByXkMQaC5Qt9UMN").call(run_input=run_input)
    dataset_id = run.get("defaultDatasetId", "")
    if not dataset_id:
        return []
    jobs = []
    for item in client.dataset(dataset_id).iterate_items():
        job_url = item.get("link", item.get("applyUrl", ""))
        if not job_url:
            continue
        jobs.append(Job(
            id=make_job_id(job_url),
            title=item.get("title", ""),
            company=item.get("companyName", ""),
            url=job_url,
            description=item.get("descriptionText", item.get("descriptionHtml", "")),
            location=item.get("location", ""),
            source="linkedin",
            posted_date=item.get("postedAt", ""),
            salary_min=0,
            salary_max=0,
        ))
    return jobs


def scout_linkedin() -> list[Job]:
    api_key = os.environ.get("APIFY_API_KEY", "")
    if not api_key:
        print("  [linkedin] skipped — no APIFY_API_KEY")
        return []

    try:
        from apify_client import ApifyClient
    except ImportError:
        print("  [linkedin] skipped — apify-client not installed")
        return []

    cfg = _load_config()
    queries = cfg.get("queries", ["Senior Product Manager payments"])
    location = cfg.get("location", "United States")
    date_posted = cfg.get("date_posted", "past-24h")

    date_map = {"past-24h": "r86400", "past-week": "r604800", "past-month": "r2592000"}
    time_filter = date_map.get(date_posted, "r86400")

    all_jobs: list[Job] = []
    # Fire all queries in parallel — wall-clock = slowest single query, not sum
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        futures = {
            pool.submit(_run_query, ApifyClient(api_key), q, location, time_filter): q
            for q in queries
        }
        for future in as_completed(futures):
            query = futures[future]
            try:
                all_jobs.extend(future.result())
            except Exception as e:
                print(f"  [linkedin] query '{query}': {e}")

    print(f"  [linkedin] {len(all_jobs)} PM jobs")
    return all_jobs
