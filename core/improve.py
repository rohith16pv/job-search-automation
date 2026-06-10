"""
Self-improvement loops — the system widens its own coverage over time.

1. discover_boards(scored)   — when a relevant job (score ≥ 50) shows up via
   LinkedIn/Indeed/Google for a company we don't track, probe that company's
   Greenhouse/Lever/Ashby board. If a live board exists, AUTO-ADD it to
   job_sources.yml so every future posting from that company arrives via the
   reliable ATS scout instead of depending on search-query luck.

2. log_blocked_title(...)    — every title the scorer hard-blocks is logged to
   data/blocked_titles.jsonl so the weekly review can spot false negatives.

3. weekly_review()           — Sundays (or forced): Claude analyzes the week's
   health history, blocked titles, and store distribution, then writes concrete
   tuning suggestions (scoring keywords, queries, companies) to
   data/improvement_suggestions.md. Suggestions are NOT auto-applied — review
   and apply them yourself (or ask Claude Code to).
"""
import json
import os
import re
from datetime import datetime, date

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "job_sources.yml")
_BLOCKED_PATH = os.path.join(_DATA_DIR, "blocked_titles.jsonl")
_DISCOVERY_PATH = os.path.join(_DATA_DIR, "board_discovery.json")
_SUGGESTIONS_PATH = os.path.join(_DATA_DIR, "improvement_suggestions.md")

_SEARCH_SOURCES = {"linkedin", "indeed", "google_careers", "wellfound"}


# ── 1. Auto-discovery of company ATS boards ──────────────────────────────────

def _slug_candidates(company: str) -> list:
    base = re.sub(r"[^a-z0-9 ]", "", (company or "").lower()).strip()
    base = re.sub(r"\b(inc|llc|corp|co|technologies|technology|labs)\b", "", base).strip()
    if not base:
        return []
    return list(dict.fromkeys([
        base.replace(" ", ""),
        base.replace(" ", "-"),
        base.split()[0] if " " in base else base,
    ]))


def _covered_slugs(cfg: dict) -> set:
    covered = set()
    for ats in ("greenhouse", "lever", "ashby"):
        covered |= {s.lower() for s in cfg.get(ats, [])}
    for entry in cfg.get("workday", []):
        covered.add(entry.get("name", "").lower())
    covered |= {s.lower() for s in cfg.get("smartrecruiters", [])}
    return covered


def _probe_board(slug: str) -> str:
    """Return the ATS name hosting a live board for this slug, or ''."""
    import requests
    ua = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    try:
        r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=8)
        if r.ok and r.json().get("jobs"):
            return "greenhouse"
    except Exception:
        pass
    try:
        r = requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=1", timeout=8)
        if r.ok and isinstance(r.json(), list) and r.json():
            return "lever"
    except Exception:
        pass
    try:
        r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", headers=ua, timeout=8)
        if r.ok and r.json().get("jobs"):
            return "ashby"
    except Exception:
        pass
    return ""


def _append_to_config(ats: str, slug: str) -> None:
    """Insert the slug at the top of its ATS section in job_sources.yml."""
    with open(_CFG_PATH) as f:
        lines = f.read().split("\n")
    header = f"{ats}:"
    idx = lines.index(header)
    lines.insert(idx + 1, f"  - {slug}  # auto-discovered {date.today()}")
    with open(_CFG_PATH, "w") as f:
        f.write("\n".join(lines))


def discover_boards(scored_jobs: list) -> list:
    """Find untracked companies among high-scoring search-sourced jobs and
    auto-add their ATS boards to config. Returns list of additions."""
    import yaml
    with open(_CFG_PATH) as f:
        cfg = yaml.safe_load(f)
    covered = _covered_slugs(cfg)

    state = {}
    try:
        with open(_DISCOVERY_PATH) as f:
            state = json.load(f)
    except Exception:
        pass
    probed = set(state.get("probed", []))

    candidates = {}
    for j in scored_jobs:
        if j.source in _SEARCH_SOURCES and j.score >= 50 and j.company:
            key = j.company.strip().lower()
            if key and key not in probed:
                candidates[key] = j.company.strip()

    additions = []
    for key, company in list(candidates.items())[:10]:  # cap per run
        probed.add(key)
        found = ""
        for slug in _slug_candidates(company):
            if slug in covered:
                found = "already-covered"
                break
            ats = _probe_board(slug)
            if ats:
                _append_to_config(ats, slug)
                covered.add(slug)
                additions.append(f"{company} → {ats}/{slug}")
                print(f"  ✚ [improve] auto-added {ats}/{slug} ({company}) to job_sources.yml — "
                      f"future postings arrive via the ATS scout directly")
                found = ats
                break
        if not found:
            pass  # no public board found — stays covered by search queries

    state["probed"] = sorted(probed)[-500:]
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_DISCOVERY_PATH, "w") as f:
        json.dump(state, f, indent=2)
    return additions


# ── 2. Blocked-title logging (feeds the weekly review) ──────────────────────

def log_blocked_title(title: str, company: str, note: str) -> None:
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_BLOCKED_PATH, "a") as f:
            f.write(json.dumps({
                "date": str(date.today()), "title": title, "company": company, "note": note,
            }) + "\n")
    except Exception:
        pass  # logging must never break scoring


def _recent_blocked(days: int = 14, limit: int = 40) -> list:
    from collections import Counter
    cutoff = None
    entries = []
    try:
        with open(_BLOCKED_PATH) as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
    except FileNotFoundError:
        return []
    counts = Counter((e["title"], e["note"]) for e in entries[-2000:])
    return [{"title": t, "note": n, "count": c} for (t, n), c in counts.most_common(limit)]


# ── 3. Weekly Claude review ──────────────────────────────────────────────────

_BURN_IN_PATH = os.path.join(_DATA_DIR, "burn_in.json")
_BURN_IN_DAYS = 7


def _in_burn_in() -> bool:
    """True during the first week after go-live — the self-review then runs on
    EVERY scan (daily) instead of Sundays only, so early breakage and scoring
    miscalibration get caught while the system is fresh."""
    try:
        with open(_BURN_IN_PATH) as f:
            start = date.fromisoformat(json.load(f)["start"])
        return (date.today() - start).days < _BURN_IN_DAYS
    except Exception:
        return False


def weekly_review(force: bool = False) -> None:
    """Claude reviews the pipeline and writes tuning suggestions to
    data/improvement_suggestions.md. Runs daily during the burn-in week,
    Sundays thereafter, or whenever force=True."""
    burn_in = _in_burn_in()
    if not force and not burn_in and date.today().weekday() != 6:
        return
    if burn_in:
        try:
            with open(_BURN_IN_PATH) as f:
                start = date.fromisoformat(json.load(f)["start"])
            day_n = (date.today() - start).days + 1
            print(f"\n[improve] Burn-in day {day_n}/{_BURN_IN_DAYS} — running daily self-review")
        except Exception:
            pass

    from core.claude_client import _claude_call

    health_hist = []
    try:
        with open(os.path.join(_DATA_DIR, "health_history.json")) as f:
            health_hist = json.load(f)[-7:]
    except Exception:
        pass

    store_summary = {}
    borderline_titles = []
    try:
        with open(os.path.join(_DATA_DIR, "jobs_store.json")) as f:
            store = json.load(f)
        jobs = store if isinstance(store, list) else list(store.values())
        from collections import Counter
        store_summary = {
            "total": len(jobs),
            "by_band": dict(Counter(
                "P0" if (j.get("score") or 0) >= 70 else
                "P1" if (j.get("score") or 0) >= 50 else
                "P2" if (j.get("score") or 0) >= 40 else "dropped"
                for j in jobs)),
            "by_source": dict(Counter(j.get("source") for j in jobs)),
        }
        # Borderline/dropped titles — the band where miscalibration hides
        borderline_titles = [
            {"title": j.get("title"), "company": j.get("company"), "score": j.get("score")}
            for j in sorted(jobs, key=lambda x: x.get("score") or 0)
            if (j.get("score") or 0) < 55
        ][:40]
    except Exception:
        pass

    print("\n[improve] Running weekly self-review via Claude...")
    try:
        result = _claude_call(
            "You are auditing a job-search pipeline for a Senior PM targeting payments/fintech roles "
            "(IC level: Senior PM / PM II-III; too senior: Director+; too junior: APM). "
            "Your goal: make sure NO relevant posting is being missed. Return only valid JSON.",
            f"""Pipeline data from the last week:

SCOUT COUNTS PER RUN (job volume per source):
{json.dumps(health_hist, indent=1)[:2500]}

TITLES HARD-BLOCKED BY THE SCORER (top, with counts — look for FALSE NEGATIVES,
i.e. titles a Senior PM in payments should have seen but the blocker killed):
{json.dumps(_recent_blocked(), indent=1)[:3000]}

STORE DISTRIBUTION: {json.dumps(store_summary)}

BORDERLINE / DROPPED TITLES (scored <55 — check for jobs that deserve more;
a relevant payments PM role sitting at 45 means the scoring is miscalibrated):
{json.dumps(borderline_titles, indent=1)[:2500]}

Return JSON:
{{"false_negative_titles": ["<blocked titles that look like real targets, if any>"],
 "scoring_suggestions": ["<concrete scoring.yml changes, e.g. add keyword X to perfect/domain>"],
 "query_suggestions": ["<new LinkedIn/Indeed query strings worth adding>"],
 "source_concerns": ["<sources whose volume trend looks broken>"],
 "other": ["<anything else that risks missing postings>"]}}""",
        )
    except Exception as e:
        print(f"  [improve] weekly review failed: {e}")
        return

    lines = [f"\n## Review — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
    for key, label in [
        ("false_negative_titles", "Possible false-negative titles (scorer blocked these)"),
        ("scoring_suggestions", "Scoring config suggestions"),
        ("query_suggestions", "Query suggestions"),
        ("source_concerns", "Source health concerns"),
        ("other", "Other"),
    ]:
        items = result.get(key) or []
        if items:
            lines.append(f"### {label}")
            lines += [f"- {i}" for i in items]
            lines.append("")

    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_SUGGESTIONS_PATH, "a") as f:
        f.write("\n".join(lines))

    print(f"  [improve] weekly review written to {_SUGGESTIONS_PATH}:")
    for line in lines[1:]:
        print(f"    {line}")
