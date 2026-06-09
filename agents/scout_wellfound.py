"""
Wellfound (AngelList) scout.
Uses Apify if available, otherwise falls back to a lightweight HTTP scrape
of Wellfound's public job search (no login required for basic listings).
"""
import asyncio
import os
import re
import yaml
import aiohttp
from .base import Job, make_job_id

_PM_SIGNALS = ["product manager", "head of product", "director of product", "staff pm", "principal pm"]


def _load_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
    with open(cfg_path) as f:
        return yaml.safe_load(f).get("wellfound", {})


async def _scrape_wellfound(session: aiohttp.ClientSession, query: str) -> list[Job]:
    """Lightweight public scrape — catches roles Wellfound exposes without login."""
    jobs = []
    try:
        url = f"https://wellfound.com/jobs?role=product-manager&keywords={query.replace(' ', '+')}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        }
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()

        # Extract job JSON blobs from embedded script tags (Wellfound uses Next.js)
        matches = re.findall(r'"jobListings":\s*(\[.*?\])', html, re.DOTALL)
        for block in matches[:1]:
            import json
            try:
                listings = json.loads(block)
                for item in listings:
                    title = item.get("title", "")
                    if not any(s in title.lower() for s in _PM_SIGNALS):
                        continue
                    job_url = f"https://wellfound.com/jobs/{item.get('slug', '')}"
                    jobs.append(Job(
                        id=make_job_id(job_url),
                        title=title,
                        company=item.get("startup", {}).get("name", ""),
                        url=job_url,
                        description=item.get("description", ""),
                        location=item.get("locationNames", [""])[0] if item.get("locationNames") else "",
                        source="wellfound",
                        posted_date=item.get("liveStartAt", "")[:10] if item.get("liveStartAt") else "",
                    ))
            except Exception:
                pass
    except Exception as e:
        print(f"  [wellfound] '{query}': {e}")
    return jobs


async def scout_wellfound(session: aiohttp.ClientSession) -> list[Job]:
    cfg = _load_config()
    queries = cfg.get("queries", ["product manager fintech"])
    all_jobs: list[Job] = []

    results = await asyncio.gather(*[_scrape_wellfound(session, q) for q in queries], return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)

    print(f"  [wellfound] {len(all_jobs)} PM jobs")
    return all_jobs
