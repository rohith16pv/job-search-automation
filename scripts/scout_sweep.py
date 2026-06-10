"""
Scout sweep — runs all free (non-Apify) scouts and prints per-source counts.
NO scoring, NO sheet writes, NO seen-marking: safe to run any number of times.
Used by /job-auto-improve to verify fixes live, and handy standalone:

    python3 scripts/scout_sweep.py
"""
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

import aiohttp


async def main() -> int:
    from agents.scout_greenhouse import scout_greenhouse
    from agents.scout_lever import scout_lever
    from agents.scout_ashby import scout_ashby
    from agents.scout_smartrecruiters import scout_smartrecruiters
    from agents.scout_workday import scout_workday
    from agents.scout_google_careers import scout_google_careers
    from agents.scout_amazon_jobs import scout_amazon_jobs
    from agents.scout_apple_jobs import scout_apple_jobs
    from agents.scout_wellfound import scout_wellfound

    scouts = {
        "greenhouse": scout_greenhouse,
        "lever": scout_lever,
        "ashby": scout_ashby,
        "smartrecruiters": scout_smartrecruiters,
        "workday": scout_workday,
        "google_careers": scout_google_careers,
        "amazon_jobs": scout_amazon_jobs,
        "apple_jobs": scout_apple_jobs,
        "wellfound": scout_wellfound,
    }
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        results = await asyncio.gather(
            *[f(session) for f in scouts.values()], return_exceptions=True
        )

    print("\n──── SWEEP SUMMARY (free sources; LinkedIn/Indeed excluded — they cost Apify credits)")
    total = 0
    errors = 0
    for name, r in zip(scouts, results):
        if isinstance(r, Exception):
            errors += 1
            print(f"  {name:18} ERROR: {type(r).__name__}: {str(r)[:90]}")
        else:
            total += len(r)
            sample = f"  e.g. {r[0].company}: {r[0].title[:42]}" if r else ""
            print(f"  {name:18} {len(r):4} jobs{sample}")
    print(f"  {'TOTAL':18} {total}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
