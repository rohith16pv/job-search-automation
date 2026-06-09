"""
Apple Jobs scout — uses the public Apple Jobs role search API.
No authentication required.
"""
import aiohttp
from .base import Job, make_job_id

_PM_TITLE_SIGNALS = [
    "product manager", "product lead", "head of product",
    "director of product", "vp of product", "group product manager",
    "principal product", "staff product",
]

_BASE = "https://jobs.apple.com/api/role/search"


def _is_pm_title(title: str) -> bool:
    t = title.lower()
    return any(sig in t for sig in _PM_TITLE_SIGNALS)


async def scout_apple_jobs(session: aiohttp.ClientSession) -> list[Job]:
    jobs: list[Job] = []
    params = {
        "query": "product manager",
        "location": "united-states",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; JobScout/1.0)",
    }
    try:
        async with session.get(
            _BASE, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                print(f"  [apple_jobs] HTTP {resp.status}")
                return []
            data = await resp.json(content_type=None)

        for item in data.get("searchResults", []):
            title = item.get("postingTitle", "")
            if not _is_pm_title(title):
                continue
            job_id = item.get("positionId", "")
            url = f"https://jobs.apple.com/en-us/details/{job_id}" if job_id else ""
            locations = item.get("locations", [])
            location = locations[0] if locations else ""
            posted_raw = item.get("postDateInGMT", "")
            posted_date = posted_raw[:10] if posted_raw else ""
            jobs.append(Job(
                id=make_job_id(url or title + "apple"),
                title=title,
                company="Apple",
                url=url,
                description=item.get("jobSummary", ""),
                location=location,
                source="apple_jobs",
                posted_date=posted_date,
            ))
    except Exception as e:
        print(f"  [apple_jobs] {e}")

    print(f"  [apple_jobs] {len(jobs)} PM jobs")
    return jobs
