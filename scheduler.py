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


def _run_job():
    print(f"\n[scheduler] Triggering run at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    try:
        asyncio.run(_import_and_run())
    except Exception as e:
        # Keep the daemon alive for tomorrow's run, but announce the failure loudly.
        print("\n" + "!" * 60)
        print(f"  [scheduler] RUN FAILED at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"  {e}")
        print("  Fix the issue above — the scheduler will try again at the next slot.")
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
    def _catch_up_if_behind():
        from core.health import hours_since_last_run
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
