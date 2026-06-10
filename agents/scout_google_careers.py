"""
Google Careers scout — the old careers.google.com/api/v3 endpoint is gone, so
this parses the public results page at google.com/about/careers/applications.
Job IDs + slugs are extracted from the HTML; descriptions and locations are
pulled from each job's detail page (capped to keep runs fast).
"""
import asyncio
import re
import aiohttp
from .base import Job, make_job_id, is_pm_title

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
_BASE = "https://www.google.com/about/careers/applications"
_QUERIES = ['"product manager" payments', '"product manager" fintech']
_MAX_DETAILS = 12

_SLUG_RE = re.compile(r"jobs/results/(\d+)-([a-z0-9-]+)")
_LOC_RE = re.compile(r'"([A-Z][A-Za-z .]+(?:, [A-Z]{2})?, USA)"')


def _title_from_slug(slug: str) -> str:
    words = slug.replace("-", " ").split()
    keep_upper = {"pm", "api", "ai", "ml", "ux", "youtube", "gcp"}
    return " ".join(w.upper() if w in keep_upper else w.capitalize() for w in words)


async def _fetch_detail(session: aiohttp.ClientSession, url: str) -> tuple:
    """Return (description, location) from a job detail page, best-effort."""
    try:
        async with session.get(url, headers=_UA, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                return "", "United States"
            html = await resp.text()
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        m = re.search(r"About the job(.{0,3000})", text)
        description = m.group(1).strip() if m else ""
        locs = _LOC_RE.findall(html)
        location = locs[0] if locs else "United States"
        return description, location
    except Exception:
        return "", "United States"


async def scout_google_careers(session: aiohttp.ClientSession) -> list[Job]:
    seen: dict = {}  # id → slug
    try:
        for q in _QUERIES:
            url = f"{_BASE}/jobs/results?q={q.replace(' ', '%20')}&location=United%20States"
            async with session.get(url, headers=_UA, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                if resp.status != 200:
                    print(f"  [google_careers] HTTP {resp.status}")
                    continue
                html = await resp.text()
            for job_id, slug in _SLUG_RE.findall(html):
                seen.setdefault(job_id, slug)
    except Exception as e:
        print(f"  [google_careers] {e}")
        return []

    candidates = [
        (job_id, slug) for job_id, slug in seen.items()
        if is_pm_title(slug.replace("-", " "))
    ][:_MAX_DETAILS]

    jobs: list[Job] = []
    details = await asyncio.gather(
        *[_fetch_detail(session, f"{_BASE}/jobs/results/{jid}-{slug}") for jid, slug in candidates],
        return_exceptions=True,
    )
    for (job_id, slug), det in zip(candidates, details):
        description, location = det if isinstance(det, tuple) else ("", "United States")
        job_url = f"{_BASE}/jobs/results/{job_id}-{slug}"
        jobs.append(Job(
            id=make_job_id(job_url),
            title=_title_from_slug(slug),
            company="Google",
            url=job_url,
            description=description,
            location=location,
            source="google_careers",
            posted_date="",  # not exposed on the public page
        ))

    print(f"  [google_careers] {len(jobs)} PM jobs")
    return jobs
