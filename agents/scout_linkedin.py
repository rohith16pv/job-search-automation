"""
LinkedIn Jobs scout — uses Apify's LinkedIn Jobs Scraper actor.
Requires APIFY_API_KEY in .env. Skipped gracefully if key is missing.
"""
import os
import yaml
from .base import Job, make_job_id


def _load_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
    with open(cfg_path) as f:
        return yaml.safe_load(f).get("linkedin", {})


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

    client = ApifyClient(api_key)
    all_jobs: list[Job] = []

    for query in queries:
        search_url = (
            f"https://www.linkedin.com/jobs/search/"
            f"?keywords={query.replace(' ', '%20')}"
            f"&location={location.replace(' ', '%20')}"
            f"&f_TPR={time_filter}"
            f"&f_WT=2"  # Remote
        )
        try:
            run_input = {
                "searchUrl": search_url,
                "maxItems": 50,
                "proxy": {"useApifyProxy": True},
            }
            run = client.actor("hKByXkMQaC5Qt9UMi").call(run_input=run_input)
            dataset_id = run.get("defaultDatasetId", "")
            if not dataset_id:
                continue
            for item in client.dataset(dataset_id).iterate_items():
                title = item.get("title", "")
                job_url = item.get("jobUrl", item.get("url", ""))
                if not job_url:
                    continue
                all_jobs.append(Job(
                    id=make_job_id(job_url),
                    title=title,
                    company=item.get("company", ""),
                    url=job_url,
                    description=item.get("description", ""),
                    location=item.get("location", ""),
                    source="linkedin",
                    posted_date=item.get("publishedAt", ""),
                    salary_min=item.get("salaryMin", 0) or 0,
                    salary_max=item.get("salaryMax", 0) or 0,
                ))
        except Exception as e:
            print(f"  [linkedin] query '{query}': {e}")

    print(f"  [linkedin] {len(all_jobs)} PM jobs")
    return all_jobs
