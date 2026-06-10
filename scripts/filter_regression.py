"""
Filter regression — would TODAY's filters have buried jobs we already know
are good? Re-runs the keyword/title gates over every stored job and reports
any P0/P1/P2 job that current config would block or keep away from Claude
deep-scoring. Run after ANY change to scoring.yml or the title filters:

    python3 scripts/filter_regression.py            # report only
    python3 scripts/filter_regression.py --strict   # exit 1 on regressions

No network, no Claude calls — pure local check, instant.
"""
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")


# Location-filter unit cases — (location, should_keep). US cities must never be
# dropped by substring traps ("india" in "Indianapolis"); real non-US must still drop.
_LOCATION_CASES = [
    ("Indianapolis, IN", True),
    ("Indiana, USA", True),
    ("Germantown, MD", True),
    ("San Francisco, CA", True),
    ("Bangalore, India", False),
    ("London, United Kingdom", False),
    ("Toronto, Canada", False),
    ("Remote - India", True),   # documented behavior: remote passes; AI score-caps non-US remote
    ("Remote - US", True),
    ("", True),                 # unknown location → keep
]


def check_location_filter() -> list:
    from core.filters import _is_usa_or_remote
    failures = []
    for location, should_keep in _LOCATION_CASES:
        if _is_usa_or_remote(location) != should_keep:
            verdict = "KEEP" if should_keep else "DROP"
            failures.append(f"location filter should {verdict} {location!r} but doesn't")
    return failures


def main() -> int:
    from agents.base import Job, is_pm_title
    from core.filters import _is_usa_or_remote
    from core.scorer import score_job

    loc_failures = check_location_filter()
    if loc_failures:
        print(f"⚠ {len(loc_failures)} LOCATION FILTER FAILURE(S):")
        for f in loc_failures:
            print(f"      ✗ {f}")
    else:
        print(f"✅ Location filter — all {len(_LOCATION_CASES)} unit cases pass.")

    store = json.load(open(_ROOT / "data" / "jobs_store.json"))
    jobs = store if isinstance(store, list) else list(store.values())

    known_good = [j for j in jobs if (j.get("score") or 0) >= 40]  # P0/P1/P2
    if not known_good:
        print("Store has no P0/P1/P2 jobs yet — nothing to regress against.")
        return 0

    regressions = []
    for raw in known_good:
        fields = {k: raw.get(k, "") for k in
                  ("id", "title", "company", "url", "description", "location", "source")}
        job = Job(**fields)

        problems = []
        if not _is_usa_or_remote(job.location):
            problems.append("location filter would DROP it as non-USA")
        if not is_pm_title(job.title):
            problems.append("scout title filter would REJECT it")
        score_job(job)
        title = job.score_breakdown.get("title", {})
        if isinstance(title, dict) and title.get("blocked"):
            problems.append(f"scorer hard-BLOCKS the title ({title.get('note')})")
        elif isinstance(title, dict) and title.get("pts", 0) == 0:
            problems.append("title gets 0 pts — excluded from Claude deep-scoring")
        if job.score < 30:
            problems.append(f"keyword score {job.score} < 30 — excluded from Claude deep-scoring")

        if problems:
            regressions.append((raw, problems))

    band = lambda s: "P0" if s >= 70 else "P1" if s >= 50 else "P2"
    if regressions:
        print(f"⚠ {len(regressions)} REGRESSION(S) — current filters would bury known-good jobs:")
        for raw, problems in regressions:
            print(f"\n  [{band(raw['score'])} {raw['score']}] {raw.get('company')} — {raw.get('title')}")
            for p in problems:
                print(f"      ✗ {p}")
        print("\nFix the filter change (or justify each regression) before shipping it.")
    else:
        print(f"✅ No regressions — all {len(known_good)} known P0/P1/P2 jobs still pass "
              f"the scout filter, title scoring, and the Claude-gate under current config.")

    return 1 if ((regressions or loc_failures) and "--strict" in sys.argv) else 0


if __name__ == "__main__":
    raise SystemExit(main())
