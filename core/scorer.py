"""
Job scorer — two-pass: keyword pre-filter then Gemini deep score.

Pass 1 (always runs): keyword-based 0-100, instant, no API.
Pass 2 (when GEMINI_API_KEY set): Gemini 2.0 Flash re-scores candidates ≥ 30.

score_job()       → keyword score only (used for pre-filter)
score_jobs_batch() → full two-pass scoring (used by orchestrator)
"""
import os
import re
import yaml
from agents.base import Job

_CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "scoring.yml")
_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "profile.yml")


def _load_cfg() -> dict:
    with open(_CFG_PATH) as f:
        return yaml.safe_load(f)


def load_profile() -> dict:
    with open(_PROFILE_PATH) as f:
        return yaml.safe_load(f)


def _norm(text: str) -> str:
    return text.lower()


def _score_title(title: str, cfg: dict) -> tuple[int, str, bool]:
    """
    Returns (pts, note, is_blocked).

    Check order (important — earlier tiers take priority):
      1. blockers    → 0 pts, hard reject
      2. above_level → 14 pts, above target (Staff/Principal/Group/Lead)
                       checked BEFORE perfect so bare "pm" in perfect
                       doesn't accidentally match "Staff PM" at 20 pts
      3. perfect     → 20 pts, exact target level
      4. good        → 14 pts (reserved for future use)
      5. partial     → 8 pts
      6. no match    → 0 pts, treated as blocked
    """
    t = _norm(title)
    ts = cfg["title_scoring"]

    for kw in ts.get("blockers", []):
        if kw in t:
            return 0, f"blocked: '{kw}'", True

    # above_level must be checked before perfect — prevents short keywords like
    # "pm" from matching "staff pm" / "principal pm" at full perfect score
    for kw in ts.get("above_level", []):
        if kw in t:
            pts = int(cfg["weights"]["title_match"] * 0.70)
            return pts, f"above level: '{kw}'", False

    for kw in ts.get("perfect", []):
        if kw in t:
            return cfg["weights"]["title_match"], f"perfect: '{kw}'", False

    for kw in ts.get("good", []):
        if kw in t:
            pts = int(cfg["weights"]["title_match"] * 0.70)
            return pts, f"good: '{kw}'", False

    for kw in ts.get("partial", []):
        if kw in t:
            pts = int(cfg["weights"]["title_match"] * 0.40)
            return pts, f"partial: '{kw}'", False

    return 0, "no title match", True  # unrecognised title treated as blocked


def _score_domain(text: str, cfg: dict) -> tuple[int, list[str]]:
    t = _norm(text)
    dk = cfg["domain_keywords"]
    tier1_max = 25
    tier2_max = 10

    tier1_pts = 0
    tier2_pts = 0
    matched: list[str] = []

    for kw in dk.get("tier1", []):
        if kw in t:
            tier1_pts = min(tier1_pts + 5, tier1_max)
            matched.append(kw)

    for kw in dk.get("tier2", []):
        if kw in t:
            tier2_pts = min(tier2_pts + 3, tier2_max)
            matched.append(kw)

    total = min(tier1_pts + tier2_pts, cfg["weights"]["domain_keywords"])
    return total, matched


def _score_skills(text: str, cfg: dict) -> tuple[int, list[str]]:
    t = _norm(text)
    max_pts = cfg["weights"]["skills_match"]
    total = 0
    matched: list[str] = []
    for entry in cfg.get("skills_keywords", []):
        if entry["keyword"] in t:
            total = min(total + entry["points"], max_pts)
            matched.append(entry["keyword"])
    return total, matched


def _score_seniority(text: str, cfg: dict) -> tuple[int, str]:
    t = _norm(text)
    ss = cfg["seniority_signals"]
    max_pts = cfg["weights"]["seniority_match"]
    for kw in ss.get("too_junior", []):
        if kw in t:
            return 0, f"too junior: '{kw}'"
    for kw in ss.get("required_senior", []):
        if kw in t:
            return max_pts, f"senior signal: '{kw}'"
    for kw in ss.get("open", []):
        if kw in t:
            return int(max_pts * 0.67), f"open level: '{kw}'"
    return int(max_pts * 0.50), "seniority unspecified"


def _score_location(location: str, description: str, cfg: dict) -> tuple[int, str]:
    combined = _norm(location + " " + description[:200])
    ls = cfg["location_scoring"]
    if "remote" in combined:
        return ls["remote"], "remote"
    if "hybrid" in combined and any(us in combined for us in ["united states", "us", "new york", "san francisco", "chicago"]):
        return ls["hybrid_us"], "hybrid US"
    us_cities = ["san francisco", "new york", "seattle", "austin", "boston", "chicago", "los angeles", "denver"]
    if any(city in combined for city in us_cities) or "united states" in combined:
        return ls["us_onsite"], "US onsite"
    return ls["non_us"], "non-US or unspecified"


def score_job(job: Job, _resume_text: str = "") -> Job:
    """Score a job 0-100 and attach breakdown. Returns the mutated job."""
    cfg = _load_cfg()

    # Job description to search — use both title and description
    full_text = f"{job.title} {job.description}"

    title_pts, title_note, is_blocked = _score_title(job.title, cfg)
    domain_pts, domain_matched = _score_domain(full_text, cfg)
    skills_pts, skills_matched = _score_skills(full_text, cfg)
    seniority_pts, seniority_note = _score_seniority(full_text, cfg)
    location_pts, location_note = _score_location(job.location, job.description, cfg)

    # Blocked titles are hard-zeroed — domain/skills can't rescue them
    if is_blocked:
        total = 0
    else:
        total = title_pts + domain_pts + skills_pts + seniority_pts + location_pts

    job.score = min(total, 100)
    job.score_breakdown = {
        "title": {"pts": title_pts, "max": cfg["weights"]["title_match"], "note": title_note, "blocked": is_blocked},
        "domain": {"pts": domain_pts, "max": cfg["weights"]["domain_keywords"], "matched": domain_matched},
        "skills": {"pts": skills_pts, "max": cfg["weights"]["skills_match"], "matched": skills_matched},
        "seniority": {"pts": seniority_pts, "max": cfg["weights"]["seniority_match"], "note": seniority_note},
        "location": {"pts": location_pts, "max": cfg["weights"]["location"], "note": location_note},
    }
    return job


async def score_jobs_batch(jobs: list, resume_text: str = "") -> list:
    """
    Full two-pass scoring:
      1. Keyword score every job
      2. If Gemini available, deep-score candidates with keyword score >= 30
    Returns all jobs with final scores attached.
    """
    from core.gemini_client import GeminiClient, is_gemini_available

    # Pass 1: keyword score all
    for job in jobs:
        score_job(job, resume_text)

    if not is_gemini_available():
        print("  [scorer] Gemini not configured — using keyword scores only")
        return jobs

    # Only AI-score jobs that passed the title filter (title_pts > 0) AND keyword score >= 30
    candidates = [
        j for j in jobs
        if j.score >= 30 and isinstance(j.score_breakdown.get("title"), dict)
        and j.score_breakdown["title"]["pts"] > 0
    ]
    skipped = [j for j in jobs if j not in candidates]

    # Optional cap for testing: set GROQ_SCORE_LIMIT=5 in .env
    limit = int(os.environ.get("GROQ_SCORE_LIMIT", 0))
    cut = []  # candidates not AI-scored due to limit — returned with keyword scores
    if limit > 0:
        all_candidates = sorted(candidates, key=lambda j: j.score, reverse=True)
        candidates = all_candidates[:limit]
        cut = all_candidates[limit:]
        print(f"  [scorer] AI scoring top {limit} candidates (GROQ_SCORE_LIMIT={limit}, {len(cut)} kept at keyword score)")
    else:
        print(f"  [scorer] AI deep-scoring {len(candidates)} candidates (skipping {len(skipped)} blocked/low)")

    try:
        client = GeminiClient(resume_text)
        candidates = await client.score_jobs_batch(candidates)
        print(f"  [scorer] AI scoring complete")
    except Exception as e:
        print(f"  [scorer] AI error ({e}) — keeping keyword scores")

    return candidates + cut + skipped


def format_breakdown(job: Job) -> str:
    b = job.score_breakdown
    # Groq-scored jobs have flat string values; keyword-scored have nested dicts
    if b.get("source", "").startswith("groq"):
        lines = [
            f"Score: {job.score}/100  [AI scored by {b.get('source', 'groq')}]",
            f"  Title    : {b.get('title', '')}",
            f"  Domain   : {b.get('domain', '')}",
            f"  Skills   : {b.get('skills', '')}",
            f"  Seniority: {b.get('seniority', '')}",
            f"  Location : {b.get('location', '')}",
        ]
        reasons = b.get("match_reasons", [])
        if reasons:
            lines.append(f"  Why      : {'; '.join(reasons)}")
        gaps = b.get("gaps", [])
        if gaps:
            lines.append(f"  Gaps     : {'; '.join(gaps)}")
    else:
        title = b.get("title", {})
        domain = b.get("domain", {})
        skills = b.get("skills", {})
        seniority = b.get("seniority", {})
        location = b.get("location", {})
        lines = [
            f"Score: {job.score}/100  [keyword scored]",
            f"  Title   : {title.get('pts', 0)}/{title.get('max', 20)} — {title.get('note', '')}",
            f"  Domain  : {domain.get('pts', 0)}/{domain.get('max', 35)} — {', '.join(domain.get('matched', [])) or 'none'}",
            f"  Skills  : {skills.get('pts', 0)}/{skills.get('max', 25)} — {', '.join(skills.get('matched', [])) or 'none'}",
            f"  Seniority: {seniority.get('pts', 0)}/{seniority.get('max', 15)} — {seniority.get('note', '')}",
            f"  Location : {location.get('pts', 0)}/{location.get('max', 5)} — {location.get('note', '')}",
        ]
    return "\n".join(lines)
