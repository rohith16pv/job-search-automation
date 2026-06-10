"""
Workday scout — uses each tenant's public CXS search API:
  POST https://{host}/wday/cxs/{tenant}/{site}/jobs
  body: {"searchText": ..., "limit": N, "offset": 0, "appliedFacets": {}}

Config entries in job_sources.yml need: name, host, tenant, site, keyword.
Descriptions are fetched per matched job from the CXS detail endpoint
(capped per company to keep the run fast).
"""
import asyncio
import os
import re
import yaml
import aiohttp
from datetime import date, timedelta
from .base import Job, make_job_id, is_pm_title

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "Accept": "application/json"}
_MAX_DETAILS_PER_COMPANY = 15
_SEARCH_LIMIT = 20


def _load_companies() -> list[dict]:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
    with open(cfg_path) as f:
        return yaml.safe_load(f).get("workday", [])


def _posted_to_iso(posted: str) -> str:
    """Convert Workday's 'Posted Today' / 'Posted 3 Days Ago' to ISO, best-effort."""
    p = (posted or "").lower()
    if "today" in p:
        return str(date.today())
    if "yesterday" in p:
        return str(date.today() - timedelta(days=1))
    m = re.search(r"(\d+)\+?\s*day", p)
    if m:
        return str(date.today() - timedelta(days=int(m.group(1))))
    return ""


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


async def _fetch_company(session: aiohttp.ClientSession, entry: dict) -> list[Job]:
    jobs = []
    name = entry.get("name", "Company")
    try:
        host, tenant, site = entry["host"], entry["tenant"], entry["site"]
        keyword = entry.get("keyword", "product manager")
        api = f"https://{host}/wday/cxs/{tenant}/{site}"

        async with session.post(
            f"{api}/jobs",
            json={"searchText": keyword, "limit": _SEARCH_LIMIT, "offset": 0, "appliedFacets": {}},
            headers={**_UA, "Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                print(f"  [workday] {name}: search HTTP {resp.status}")
                return []
            data = await resp.json(content_type=None)

        matched = [
            item for item in data.get("jobPostings", [])
            if is_pm_title(item.get("title", ""))
        ][:_MAX_DETAILS_PER_COMPANY]

        for item in matched:
            title = item.get("title", "").strip()
            ext_path = item.get("externalPath", "")
            job_url = f"https://{host}/en-US/{site}{ext_path}"

            # Fetch description from the detail endpoint (best-effort)
            description = ""
            try:
                async with session.get(
                    f"{api}{ext_path}", headers=_UA,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as dresp:
                    if dresp.status == 200:
                        detail = await dresp.json(content_type=None)
                        description = _strip_html(
                            detail.get("jobPostingInfo", {}).get("jobDescription", "")
                        )
            except Exception:
                pass

            jobs.append(Job(
                id=make_job_id(job_url),
                title=title,
                company=name,
                url=job_url,
                description=description,
                location=item.get("locationsText", ""),
                source="workday",
                posted_date=_posted_to_iso(item.get("postedOn", "")),
            ))
    except Exception as e:
        print(f"  [workday] {name}: {e}")
    return jobs


async def scout_workday(session: aiohttp.ClientSession) -> list[Job]:
    companies = _load_companies()
    all_jobs: list[Job] = []
    results = await asyncio.gather(*[_fetch_company(session, c) for c in companies], return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)
    print(f"  [workday] {len(all_jobs)} PM jobs across {len(companies)} companies")
    return all_jobs
