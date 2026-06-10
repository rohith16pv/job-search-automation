"""
SmartRecruiters scout — uses the public SmartRecruiters jobs API.
No authentication required.
"""
import asyncio
import os
import yaml
import aiohttp
from .base import Job, make_job_id, is_pm_title

_BASE = "https://api.smartrecruiters.com/v1/companies"


def _load_companies() -> list[str]:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
    with open(cfg_path) as f:
        return yaml.safe_load(f).get("smartrecruiters", [])


async def _fetch_company(session: aiohttp.ClientSession, company: str) -> list[Job]:
    jobs = []
    try:
        url = f"{_BASE}/{company}/postings"
        params = {"status": "PUBLIC", "limit": 100, "offset": 0}
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)

        for p in data.get("content", []):
            title = p.get("name", "")
            if not is_pm_title(title):
                continue
            loc = p.get("location", {})
            location_str = ", ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country")]))
            remote = p.get("workplace", {}).get("wfhPolicy", "")
            if "remote" in remote.lower():
                location_str = f"Remote — {location_str}" if location_str else "Remote"
            jobs.append(Job(
                id=make_job_id(p.get("ref", p.get("id", ""))),
                title=title,
                company=company.title(),
                url=p.get("ref", ""),
                description=p.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", ""),
                location=location_str,
                source="smartrecruiters",
                posted_date=p.get("createdOn", "")[:10],
            ))
    except Exception as e:
        print(f"  [smartrecruiters] {company}: {e}")
    return jobs


async def scout_smartrecruiters(session: aiohttp.ClientSession) -> list[Job]:
    companies = _load_companies()
    all_jobs: list[Job] = []
    results = await asyncio.gather(*[_fetch_company(session, c) for c in companies], return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)
    print(f"  [smartrecruiters] {len(all_jobs)} PM jobs across {len(companies)} companies")
    return all_jobs
