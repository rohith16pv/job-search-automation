"""
Greenhouse ATS scout — uses the public Greenhouse boards API.
No authentication required.
"""
import asyncio
import os
from typing import Optional
import yaml
import aiohttp
from .base import Job, make_job_id, is_pm_title

_BASE = "https://boards-api.greenhouse.io/v1/boards"


def _load_companies() -> list[str]:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
    with open(cfg_path) as f:
        return yaml.safe_load(f).get("greenhouse", [])


async def _fetch_jobs(session: aiohttp.ClientSession, company: str) -> list[Job]:
    jobs = []
    try:
        list_url = f"{_BASE}/{company}/jobs"
        async with session.get(list_url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)

        candidate_ids = [
            j["id"] for j in data.get("jobs", [])
            if is_pm_title(j.get("title", ""))
        ]

        # Fetch descriptions in parallel (up to 5 at a time)
        sem = asyncio.Semaphore(5)

        async def fetch_detail(job_id: int) -> Optional[Job]:
            async with sem:
                try:
                    url = f"{_BASE}/{company}/jobs/{job_id}"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                        if r.status != 200:
                            return None
                        d = await r.json(content_type=None)
                    location = ""
                    if d.get("offices"):
                        location = d["offices"][0].get("name", "")
                    elif d.get("location", {}).get("name"):
                        location = d["location"]["name"]
                    return Job(
                        id=make_job_id(d.get("absolute_url", url)),
                        title=d.get("title", ""),
                        company=d.get("departments", [{}])[0].get("name", company.title())
                               if not d.get("company_name") else d["company_name"],
                        url=d.get("absolute_url", ""),
                        description=d.get("content", ""),
                        location=location,
                        source="greenhouse",
                        posted_date=d.get("updated_at", "")[:10],
                    )
                except Exception:
                    return None

        results = await asyncio.gather(*[fetch_detail(jid) for jid in candidate_ids])
        jobs = [j for j in results if j is not None]
    except Exception as e:
        print(f"  [greenhouse] {company}: {e}")
    return jobs


async def scout_greenhouse(session: aiohttp.ClientSession) -> list[Job]:
    companies = _load_companies()
    all_jobs: list[Job] = []
    tasks = [_fetch_jobs(session, c) for c in companies]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)
    print(f"  [greenhouse] {len(all_jobs)} PM jobs across {len(companies)} companies")
    return all_jobs
