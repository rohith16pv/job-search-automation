"""
Daily scheduler — runs orchestrator.run() on a configurable cron schedule.

Usage:
  python scheduler.py          # starts the scheduler daemon (runs until Ctrl-C)
  python scheduler.py --now    # run immediately, then exit

Schedule is controlled by JOB_SCAN_SCHEDULE in .env (default: 09:00 PT daily).
"""
import asyncio
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import schedule

# Failure backoff — every retry re-launches the full pipeline (Claude + Apify
# spend), so a failing run must NOT be relaunched on every 30s catch-up tick.
FAILURE_BACKOFF_MIN = 60        # generic failure: no catch-up retry for 1h
USAGE_LIMIT_BACKOFF_MIN = 360   # usage limit resets on multi-hour windows
MAX_CATCHUP_RETRIES = 3         # then wait for the next scheduled daily slot

_retry_blocked_until = 0.0      # monotonic-ish wall clock; 0 = no block
_consecutive_failures = 0


def _run_job():
    global _retry_blocked_until, _consecutive_failures
    from core.claude_client import ClaudeUsageLimitError
    print(f"\n[scheduler] Triggering run at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    try:
        asyncio.run(_import_and_run())
        _consecutive_failures = 0
        _retry_blocked_until = 0.0
    except ClaudeUsageLimitError as e:
        # Same condition as orchestrator's exit code 2 — retrying soon just
        # burns the subscription window. Back off for hours, not seconds.
        _consecutive_failures += 1
        _retry_blocked_until = time.time() + USAGE_LIMIT_BACKOFF_MIN * 60
        print("\n" + "!" * 60)
        print(f"  [scheduler] RUN STOPPED — CLAUDE USAGE LIMIT at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"  {e}")
        print(f"  No catch-up retry for {USAGE_LIMIT_BACKOFF_MIN // 60}h (limits reset on multi-hour windows).")
        print("!" * 60)
    except Exception as e:
        # Keep the daemon alive for tomorrow's run, but announce the failure loudly.
        _consecutive_failures += 1
        _retry_blocked_until = time.time() + FAILURE_BACKOFF_MIN * 60
        print("\n" + "!" * 60)
        print(f"  [scheduler] RUN FAILED at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"  {e}")
        if _consecutive_failures >= MAX_CATCHUP_RETRIES:
            print(f"  {_consecutive_failures} consecutive failures — catch-up retries suspended "
                  f"until the next scheduled slot. Fix the issue above.")
        else:
            print(f"  Fix the issue above — no catch-up retry for {FAILURE_BACKOFF_MIN} min "
                  f"(attempt {_consecutive_failures}/{MAX_CATCHUP_RETRIES} before waiting for the next slot).")
        print("!" * 60)


async def _import_and_run():
    from orchestrator import run
    await run()


def main():
    if "--now" in sys.argv:
        print("[scheduler] Running immediately (--now flag)")
        asyncio.run(_import_and_run())
        return

    run_time = os.environ.get("JOB_SCAN_TIME", "09:00")  # 24h format, local time
    print(f"[scheduler] Scheduled daily at {run_time}")
    print("[scheduler] Press Ctrl-C to stop\n")

    schedule.every().day.at(run_time).do(_run_job)

    # Catch-up: if the laptop was asleep/off at the scheduled time, the daily
    # job silently misses. Check the last successful scan on startup and every
    # tick — run immediately whenever we're more than 26h behind, so a missed
    # 9am can never cost a day of postings (source windows are 7 days wide).
    # Failed runs leave the gap >26h, so the gate below is what keeps a broken
    # run from being relaunched (and billed) on every 30s tick.
    def _catch_up_if_behind():
        from core.health import hours_since_last_run
        if time.time() < _retry_blocked_until:
            return  # recent failure — backing off, don't relaunch the pipeline
        if _consecutive_failures >= MAX_CATCHUP_RETRIES:
            return  # retries exhausted — only the scheduled daily slot may try again
        gap = hours_since_last_run()
        if gap > 26:
            label = f"{gap:.0f}h" if gap != float("inf") else "never"
            print(f"[scheduler] Last successful scan: {label} ago — running catch-up scan now")
            _run_job()

    _catch_up_if_behind()

    while True:
        schedule.run_pending()
        _catch_up_if_behind()
        time.sleep(30)


if __name__ == "__main__":
    main()
