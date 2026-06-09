"""
Amazon Jobs scout — uses the public Amazon Jobs JSON search API.
No authentication required.
"""
import aiohttp
from .base import Job, make_job_id

_PM_TITLE_SIGNALS = [
    "product manager", "product lead", "head of product",
    "director of product", "vp of product", "group product manager",
    "principal product", "staff product",
]

_BASE = "https://www.amazon.jobs/en/search.json"


def _is_pm_title(title: str) -> bool:
    t = title.lower()
    return any(sig in t for sig in _PM_TITLE_SIGNALS)


async def scout_amazon_jobs(session: aiohttp.ClientSession) -> list[Job]:
    jobs: list[Job] = []
    params = {
        "normalized_keywords": "product manager",
        "loc_query": "United States",
        "result_limit": "20",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; JobScout/1.0)",
    }
    try:
        async with session.get(
            _BASE, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                print(f"  [amazon_jobs] HTTP {resp.status}")
                return []
            data = await resp.json(content_type=None)

        for item in data.get("jobs", []):
            title = item.get("title", "")
            if not _is_pm_title(title):
                continue
            job_id = item.get("id_icims", item.get("job_id", ""))
            url = f"https://www.amazon.jobs/en/jobs/{job_id}" if job_id else ""
            location = item.get("location", "")
            posted_raw = item.get("posted_date", item.get("updated_time", ""))
            posted_date = posted_raw[:10] if posted_raw else ""
            jobs.append(Job(
                id=make_job_id(url or title + "amazon"),
                title=title,
                company="Amazon",
                url=url,
                description=item.get("description", item.get("job_summary", "")),
                location=location,
                source="amazon_jobs",
                posted_date=posted_date,
            ))
    except Exception as e:
        print(f"  [amazon_jobs] {e}")

    print(f"  [amazon_jobs] {len(jobs)} PM jobs")
    return jobs
