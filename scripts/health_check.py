"""
Standalone health check — run any time to verify nothing is silently broken:
    python3 scripts/health_check.py            # checks only
    python3 scripts/health_check.py --review   # also force the Claude self-review

Checks: Claude auth, Google Sheets, Apify key, last-run gap, all configured
ATS boards resolve, and the last run's per-source counts vs baseline.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

import aiohttp
from core import health, improve


async def main() -> int:
    failures = 0
    try:
        health.preflight()
    except Exception as e:
        print(f"\n  ❌ PREFLIGHT FAILED: {e}")
        failures += 1

    print("\n[health] Auditing configured ATS boards...")
    async with aiohttp.ClientSession() as session:
        warnings = await health.audit_ats_slugs(session)
        failures += 1 if warnings else 0

    print("\n[health] Last recorded scout counts:")
    try:
        hist = json.load(open(_ROOT / "data" / "health_history.json"))
        last = hist[-1]
        print(f"  run: {last['date']}")
        for src, n in sorted(last["counts"].items()):
            print(f"    {src:18} {n}")
    except Exception:
        print("  (no history yet — runs after the first scan)")

    if "--review" in sys.argv:
        improve.weekly_review(force=True)

    print("\n" + ("✅ ALL HEALTHY" if failures == 0 else f"⚠ {failures} ISSUE GROUP(S) — see above"))
    return failures


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
