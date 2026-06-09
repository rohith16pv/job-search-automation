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
    asyncio.run(_import_and_run())


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

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
