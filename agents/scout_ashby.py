"""
Ashby ATS scout — uses the public posting API (GET, no authentication):
  https://api.ashbyhq.com/posting-api/job-board/{company}
"""
import asyncio
import os
import yaml
import aiohttp
from .base import Job, make_job_id, is_pm_title

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def _load_companies() -> list[str]:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
    with open(cfg_path) as f:
        return yaml.safe_load(f).get("ashby", [])


async def _fetch_company(session: aiohttp.ClientSession, company: str) -> list[Job]:
    jobs = []
    try:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
        async with session.get(url, headers=_UA, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)

        for p in data.get("jobs", []):
            title = p.get("title", "").strip()
            if not p.get("isListed", True) or not is_pm_title(title):
                continue
            job_url = p.get("jobUrl") or f"https://jobs.ashbyhq.com/{company}/{p.get('id', '')}"
            location = p.get("location", "") or ""
            if p.get("isRemote") and "remote" not in location.lower():
                location = f"Remote — {location}" if location else "Remote"
            published = p.get("publishedAt", "") or ""
            jobs.append(Job(
                id=make_job_id(job_url),
                title=title,
                company=company.replace("-", " ").title(),
                url=job_url,
                description=p.get("descriptionPlain", "") or "",
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
