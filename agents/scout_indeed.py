"""
Indeed scout — uses Apify's Indeed scraper actor.
Requires APIFY_API_KEY in .env. Skipped gracefully if key is missing.
"""
import os
import yaml
from .base import Job, make_job_id


def _load_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
    with open(cfg_path) as f:
        return yaml.safe_load(f).get("indeed", {})


def scout_indeed() -> list[Job]:
    api_key = os.environ.get("APIFY_API_KEY", "")
    if not api_key:
        print("  [indeed] skipped — no APIFY_API_KEY")
        return []

    try:
        from apify_client import ApifyClient
    except ImportError:
        print("  [indeed] skipped — apify-client not installed")
        return []

    cfg = _load_config()
    queries = cfg.get("queries", ["Senior Product Manager payments"])
    location = cfg.get("location", "United States")
    date_posted = cfg.get("date_posted", "1")

    client = ApifyClient(api_key)
    all_jobs: list[Job] = []

    for query in queries:
        try:
            run_input = {
                "keyword": query,
                "location": location,
                "maxItems": 50,
                "fromAge": int(date_posted),
                "proxy": {"useApifyProxy": True},
            }
            run = client.actor("misceres/indeed-scraper").call(run_input=run_input)
            dataset_id = run.get("defaultDatasetId", "")
            if not dataset_id:
                continue
            for item in client.dataset(dataset_id).iterate_items():
                job_url = item.get("url", item.get("jobUrl", ""))
                if not job_url:
                    continue
                all_jobs.append(Job(
                    id=make_job_id(job_url),
                    title=item.get("positionName", item.get("title", "")),
                    company=item.get("company", ""),
                    url=job_url,
                    description=item.get("description", ""),
                    location=item.get("location", ""),
                    source="indeed",
                    posted_date=item.get("postedAt", ""),
                    salary_min=item.get("salaryMin", 0) or 0,
                    salary_max=item.get("salaryMax", 0) or 0,
                ))
        except Exception as e:
            print(f"  [indeed] query '{query}': {e}")

    print(f"  [indeed] {len(all_jobs)} jobs")
    return all_jobs
