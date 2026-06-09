"""
Lever ATS scout — uses the public Lever postings API.
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

_BASE = "https://api.lever.co/v0/postings"


def _load_companies() -> list[str]:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
    with open(cfg_path) as f:
        return yaml.safe_load(f).get("lever", [])


def _is_pm_title(title: str) -> bool:
    t = title.lower()
    return any(sig in t for sig in _PM_TITLE_SIGNALS)


def _parse_salary(text: str) -> tuple[int, int]:
    import re
    nums = re.findall(r"\$?([\d,]+)", text.replace(",", ""))
    parsed = [int(n) for n in nums if int(n) > 50000]
    if len(parsed) >= 2:
        return parsed[0], parsed[1]
    if len(parsed) == 1:
        return parsed[0], parsed[0]
    return 0, 0


async def _fetch_company(session: aiohttp.ClientSession, company: str) -> list[Job]:
    jobs = []
    try:
        url = f"{_BASE}/{company}?mode=json&commitment=Full-time"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return []
            postings = await resp.json(content_type=None)

        for p in postings:
            title = p.get("text", "")
            if not _is_pm_title(title):
                continue

            cats = p.get("categories", {})
            location = cats.get("location", "") or cats.get("allLocations", [""])[0]
            desc_plain = p.get("descriptionPlain", "") or ""
            salary_text = p.get("salaryRange", {}) or {}
            sal_min = salary_text.get("min", 0) or 0
            sal_max = salary_text.get("max", 0) or 0
            if not sal_min:
                sal_min, sal_max = _parse_salary(desc_plain[:500])

            created_ms = p.get("createdAt") or 0
            if created_ms:
                from datetime import datetime, timezone
                posted_date = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            else:
                posted_date = ""

            jobs.append(Job(
                id=make_job_id(p.get("hostedUrl", p.get("id", ""))),
                title=title,
                company=p.get("company", company.title()),
                url=p.get("hostedUrl", ""),
                description=desc_plain,
                location=location,
                source="lever",
                posted_date=posted_date,
                salary_min=sal_min,
                salary_max=sal_max,
            ))
    except Exception as e:
        print(f"  [lever] {company}: {e}")
    return jobs


async def scout_lever(session: aiohttp.ClientSession) -> list[Job]:
    companies = _load_companies()
    all_jobs: list[Job] = []
    results = await asyncio.gather(*[_fetch_company(session, c) for c in companies], return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)
    print(f"  [lever] {len(all_jobs)} PM jobs across {len(companies)} companies")
    return all_jobs
