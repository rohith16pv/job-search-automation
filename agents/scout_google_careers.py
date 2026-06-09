"""
Google Careers scout — uses the public Google Careers JSON API.
No authentication required.
"""
import aiohttp
from .base import Job, make_job_id

_PM_TITLE_SIGNALS = [
    "product manager", "product lead", "head of product",
    "director of product", "vp of product", "group product manager",
    "principal product", "staff product",
]

_BASE = "https://careers.google.com/api/v3/search/"


def _is_pm_title(title: str) -> bool:
    t = title.lower()
    return any(sig in t for sig in _PM_TITLE_SIGNALS)


async def scout_google_careers(session: aiohttp.ClientSession) -> list[Job]:
    jobs: list[Job] = []
    params = {
        "q": "product manager",
        "location": "United States",
        "page_size": "20",
    }
    try:
        async with session.get(_BASE, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                print(f"  [google_careers] HTTP {resp.status}")
                return []
            data = await resp.json(content_type=None)

        for item in data.get("jobs", []):
            title = item.get("title", "")
            if not _is_pm_title(title):
                continue
            job_id = item.get("id", "")
            url = f"https://careers.google.com/jobs/results/{job_id}" if job_id else ""
            locations = item.get("locations", [])
            location = locations[0].get("display", "") if locations else ""
            # posted date: e.g. "2024-01-15T00:00:00Z"
            posted_raw = item.get("modified", item.get("published", ""))
            posted_date = posted_raw[:10] if posted_raw else ""
            jobs.append(Job(
                id=make_job_id(url or title + "google"),
                title=title,
                company="Google",
                url=url,
                description=item.get("description", ""),
                location=location,
                source="google_careers",
                posted_date=posted_date,
            ))
    except Exception as e:
        print(f"  [google_careers] {e}")

    print(f"  [google_careers] {len(jobs)} PM jobs")
    return jobs
