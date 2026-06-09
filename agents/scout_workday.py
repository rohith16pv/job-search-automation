"""
Workday scout — config-driven scrape of individual Workday career pages.
Each company has a unique Workday subdomain; we hit their public job search API.
Requires APIFY_API_KEY for JS-heavy pages, else falls back to a simple GET.
"""
import asyncio
import os
import re
import yaml
import aiohttp
from .base import Job, make_job_id

_PM_SIGNALS = ["product manager", "head of product", "director of product", "staff pm", "principal pm"]


def _load_companies() -> list[dict]:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
    with open(cfg_path) as f:
        return yaml.safe_load(f).get("workday", [])


async def _fetch_workday_api(session: aiohttp.ClientSession, entry: dict) -> list[Job]:
    """
    Workday exposes a semi-public search API at:
    /wday/cxs/{tenant}/{instance}/jobs  (POST with JSON body)
    This pattern works for many but not all Workday instances.
    """
    jobs = []
    try:
        name = entry.get("name", "Company")
        base_url = entry.get("url", "")
        keyword = entry.get("keyword", "product manager")

        # Try to infer the Workday API path from the URL
        # Pattern: https://wd5.myworkday.com/{company}/d/jobs → API at /wday/cxs/{company}/FW_v1/jobs
        match = re.search(r"myworkday\.com/([^/]+)", base_url)
        if not match:
            return []
        tenant = match.group(1)
        api_url = f"https://www.myworkday.com/wday/cxs/{tenant}/FW_v1/jobs"
        payload = {
            "appliedFacets": {},
            "limit": 20,
            "offset": 0,
            "searchText": keyword,
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        async with session.post(api_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)

        for item in data.get("jobPostings", []):
            title = item.get("title", "")
            if not any(s in title.lower() for s in _PM_SIGNALS):
                continue
            ext_path = item.get("externalPath", "")
            job_url = f"https://www.myworkday.com{ext_path}" if ext_path else base_url
            location = item.get("locationsText", "")
            jobs.append(Job(
                id=make_job_id(job_url),
                title=title,
                company=name,
                url=job_url,
                description=item.get("jobDescription", ""),
                location=location,
                source="workday",
                posted_date=item.get("postedOn", "")[:10] if item.get("postedOn") else "",
            ))
    except Exception as e:
        print(f"  [workday] {entry.get('name', '?')}: {e}")
    return jobs


async def scout_workday(session: aiohttp.ClientSession) -> list[Job]:
    companies = _load_companies()
    all_jobs: list[Job] = []
    results = await asyncio.gather(*[_fetch_workday_api(session, c) for c in companies], return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)
    print(f"  [workday] {len(all_jobs)} PM jobs across {len(companies)} companies")
    return all_jobs
