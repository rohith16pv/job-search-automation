"""
Apple Jobs scout — the JSON search APIs require CSRF tokens, so this parses
the server-rendered search page at jobs.apple.com/en-us/search instead.
Detail links are extracted from the HTML; descriptions come from each
job's detail page (capped to keep runs fast).
"""
import asyncio
import re
import aiohttp
from .base import Job, make_job_id, is_pm_title

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
_BASE = "https://jobs.apple.com"
_QUERIES = ["product manager payments", "product manager wallet"]
_MAX_DETAILS = 10

_DETAIL_RE = re.compile(r"/en-us/details/(\d+)/([a-z0-9-]+)")


def _title_from_slug(slug: str) -> str:
    words = slug.replace("-", " ").split()
    keep_upper = {"pm", "api", "ai", "ml", "ios", "macos"}
    return " ".join(w.upper() if w in keep_upper else w.capitalize() for w in words)


async def _fetch_detail(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, headers=_UA, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                return ""
            html = await resp.text()
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        m = re.search(r"(?:Summary|Description)(.{0,3000})", text)
        return m.group(1).strip() if m else ""
    except Exception:
        return ""


async def scout_apple_jobs(session: aiohttp.ClientSession) -> list[Job]:
    seen: dict = {}  # id → slug
    try:
        for q in _QUERIES:
            url = f"{_BASE}/en-us/search?search={q.replace(' ', '%20')}&sort=newest&location=united-states-USA"
            async with session.get(url, headers=_UA, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                if resp.status != 200:
                    print(f"  [apple_jobs] HTTP {resp.status}")
                    continue
                html = await resp.text()
            for job_id, slug in _DETAIL_RE.findall(html):
                seen.setdefault(job_id, slug)
    except Exception as e:
        print(f"  [apple_jobs] {e}")
        return []

    candidates = [
        (job_id, slug) for job_id, slug in seen.items()
        if is_pm_title(slug.replace("-", " "))
    ][:_MAX_DETAILS]

    jobs: list[Job] = []
    details = await asyncio.gather(
        *[_fetch_detail(session, f"{_BASE}/en-us/details/{jid}/{slug}") for jid, slug in candidates],
        return_exceptions=True,
    )
    for (job_id, slug), desc in zip(candidates, details):
        job_url = f"{_BASE}/en-us/details/{job_id}/{slug}"
        jobs.append(Job(
            id=make_job_id(job_url),
            title=_title_from_slug(slug),
            company="Apple",
            url=job_url,
            description=desc if isinstance(desc, str) else "",
            location="United States",
            source="apple_jobs",
            posted_date="",
        ))

    if jobs:
        print(f"  [apple_jobs] {len(jobs)} PM jobs")
    else:
        print("  [apple_jobs] 0 PM jobs — Apple renders results client-side behind CSRF; "
              "Apple PM roles are covered by the LinkedIn payment queries")
    return jobs
