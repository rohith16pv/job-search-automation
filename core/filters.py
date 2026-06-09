"""
Hard pre-filters applied after dedup, before scoring.
Drops jobs clearly outside the USA or posted more than max_days ago.

Safe defaults:
- Empty location  → keep (can't tell)
- "remote" anywhere in location → keep (AI will handle non-US remote)
- Empty posted_date → keep (can't tell; Lever/Workday may not always provide it)
"""
from datetime import date, timedelta

# Unambiguous non-US signals — long enough to avoid false positives on US locations.
# "paris" included because Paris, TX has no meaningful tech PM market.
# "vancouver" included because Vancouver BC vastly outnumbers Vancouver WA for PM roles.
_NON_US_SIGNALS = frozenset([
    # UK / Europe
    "united kingdom", "london", "manchester", "edinburgh", "bristol",
    "germany", "berlin", "munich", "hamburg", "frankfurt",
    "france", "paris", "lyon",
    "netherlands", "amsterdam",
    "spain", "madrid", "barcelona",
    "sweden", "stockholm",
    "norway", "oslo",
    "denmark", "copenhagen",
    "switzerland", "zurich",
    "austria", "vienna",
    "belgium", "brussels",
    "finland", "helsinki",
    "portugal", "lisbon",
    "poland", "warsaw",
    "ireland", "dublin",
    "italy", "milan", "rome",
    "czech republic", "prague",
    # Americas (non-US)
    "canada", "toronto", "vancouver", "montreal", "ottawa", "calgary",
    "brazil", "são paulo", "sao paulo", "rio de janeiro",
    "argentina", "buenos aires",
    "colombia", "bogotá", "bogota",
    "chile", "santiago",
    "mexico city",
    # Asia / Pacific
    "india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad",
    "pune", "chennai", "kolkata",
    "singapore",
    "australia", "sydney", "melbourne", "brisbane", "perth",
    "new zealand", "auckland",
    "japan", "tokyo", "osaka",
    "china", "beijing", "shanghai", "shenzhen",
    "south korea", "seoul",
    "hong kong",
    "taiwan", "taipei",
    # Middle East / Africa
    "israel", "tel aviv",
    "united arab emirates", "dubai", "abu dhabi",
    "south africa", "johannesburg", "cape town",
])

_REMOTE_SIGNALS = ("remote", "work from home", "wfh", "distributed")


def _is_usa_or_remote(location: str) -> bool:
    """True if the job is in the USA or explicitly remote (pass through)."""
    if not location:
        return True
    loc = location.lower()
    # Remote roles pass through — AI will handle non-US-remote with its score cap
    if any(s in loc for s in _REMOTE_SIGNALS):
        return True
    # Check for clear non-US signals
    for signal in _NON_US_SIGNALS:
        if signal in loc:
            return False
    return True  # unrecognised or clearly US — keep


def _is_within_days(posted_date: str, days: int = 7) -> bool:
    """True if posted within `days` days of today, or if date is unknown."""
    if not posted_date:
        return True
    try:
        posted = date.fromisoformat(posted_date[:10])
        return posted >= date.today() - timedelta(days=days)
    except (ValueError, TypeError):
        return True


def apply_hard_filters(jobs: list, max_days: int = 7) -> tuple[list, dict]:
    """
    Apply USA-only and recency filters. Returns (kept_jobs, stats_dict).
    Jobs with empty location or empty posted_date always pass through.
    """
    kept = []
    non_usa = 0
    stale = 0
    for job in jobs:
        if not _is_usa_or_remote(job.location):
            non_usa += 1
            continue
        if not _is_within_days(job.posted_date, max_days):
            stale += 1
            continue
        kept.append(job)
    return kept, {"non_usa": non_usa, "stale": stale, "kept": len(kept)}
