"""
Ashby ATS scout — uses the Ashby public discovery feed.
No authentication required.
"""
import asyncio
import os
import yaml
import aiohttp
from .base import Job, make_job_id

_PM_TITLE_SIGNALS = [
    "product manager", "product lead", "head of product",
    "director of product", "vp of product", "group product manager",
    "principal product", "staff product",
]


def _load_companies() -> list[str]:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
    with open(cfg_path) as f:
        return yaml.safe_load(f).get("ashby", [])


def _is_pm_title(title: str) -> bool:
    return any(sig in title.lower() for sig in _PM_TITLE_SIGNALS)


async def _fetch_company(session: aiohttp.ClientSession, company: str) -> list[Job]:
    jobs = []
    try:
        url = (
            "https://jobs.ashbyhq.com/api/non-user-facing/job-board/discovery-feed"
            f"?organizationHostedJobsPageName={company}"
        )
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)

        for p in data.get("jobPostings", []):
            title = p.get("title", "")
            if not _is_pm_title(title):
                continue
            job_id = p.get("id", "")
            job_url = f"https://jobs.ashbyhq.com/{company}/{job_id}"
            location = p.get("locationName", "") or p.get("employmentType", "")
            published = p.get("publishedDate", "")
            jobs.append(Job(
                id=make_job_id(job_url),
                title=title,
                company=data.get("organization", {}).get("name", company.title()),
                url=job_url,
                description=p.get("descriptionPlain", ""),
                location=location,
                source="ashby",
                posted_date=published[:10] if published else "",
            ))
    except Exception as e:
        print(f"  [ashby] {company}: {e}")
    return jobs


async def scout_ashby(session: aiohttp.ClientSession) -> list[Job]:
    companies = _load_companies()
    all_jobs: list[Job] = []
    results = await asyncio.gather(*[_fetch_company(session, c) for c in companies], return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)
    print(f"  [ashby] {len(all_jobs)} PM jobs across {len(companies)} companies")
    return all_jobs
