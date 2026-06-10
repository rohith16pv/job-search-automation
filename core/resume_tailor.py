"""
Resume tailor — generates targeted resume suggestions for a specific job.

Uses Claude (your subscription, via claude CLI) to write a reworded summary,
pick the best bullets, add missing keywords, and suggest section order changes.

Claude is REQUIRED — if the CLI is missing or not logged in, this module raises
ClaudeUnavailableError and the run aborts. There is no keyword-only fallback.

Output:
  - If Google Docs credentials exist → creates a GDoc and returns the URL.
  - Otherwise → saves locally to data/tailored/ and returns file path.
"""
import json
import os
import re
from agents.base import Job

_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "tailored")
_CACHE_DIR = os.path.join(_OUTPUT_DIR, ".pending")  # Claude output awaiting GDoc creation

_SECTION_SIGNALS = {
    "payments": ["payment", "settlement", "ach", "rtp", "rail", "treasury", "liquidity", "money movement"],
    "api_platform": ["api", "platform", "developer", "sdk", "webhook", "integration", "embedded"],
    "compliance": ["compliance", "regulatory", "psd2", "apra", "risk", "fraud", "kyc", "aml"],
    "data_analytics": ["data", "analytics", "metrics", "sql", "tableau", "a/b test", "experimentation"],
    "cross_functional": ["cross-functional", "stakeholder", "roadmap", "okr", "planning", "strategy"],
    "scale": ["scale", "infrastructure", "volume", "reliability", "uptime", "latency", "performance"],
}

_RESUME_HIGHLIGHTS = {
    "payments": [
        "Scaled payments platform to $1B+ GMV with 99.99% uptime",
        "Reduced settlement time from T+2 to T+0 for 95% of transactions",
        "Built RTP integration reducing settlement time by 90%",
        "ACH product line scaled from $50M to $300M GMV in 18 months",
    ],
    "api_platform": [
        "Designed embedded finance API → 150+ customers, $50M ARR",
        "Led API-first product design for fintech partner integrations",
    ],
    "compliance": [
        "Regulatory expansion into 5 markets (UK, EU, APAC) — $40M revenue impact",
        "Worked with Legal/Compliance on PSD2, APRA, BNM frameworks",
    ],
    "data_analytics": [
        "Built ML-powered fraud detection: 80% reduction in false declines, 1.9x revenue impact",
        "Defined success metrics and data pipeline for iterative model improvements",
    ],
    "cross_functional": [
        "Led cross-functional team of 12 engineers across 3 time zones",
        "OKR-driven planning framework across engineering, design, operations, legal",
    ],
    "scale": [
        "Zero-downtime migration to handle 100x volume growth — $2B+ daily volume",
        "Infrastructure redesign: 99.99% uptime at scale",
    ],
}


def _extract_requirements(description: str) -> list[str]:
    """Pull key requirement bullets from job description."""
    lines = description.split("\n")
    req_lines = []
    in_requirements = False
    for line in lines:
        line = line.strip()
        if re.search(r"requirement|qualification|what you.ll|what we.re|you have|you bring", line, re.I):
            in_requirements = True
        if in_requirements and re.match(r"^[-•*]\s+|^\d+\.\s+", line):
            req_lines.append(line.lstrip("•*-123456789. "))
        if in_requirements and not line and len(req_lines) > 3:
            in_requirements = False
    return req_lines[:15]


def _detect_themes(description: str) -> list[str]:
    d = description.lower()
    themes = []
    for theme, signals in _SECTION_SIGNALS.items():
        if sum(1 for s in signals if s in d) >= 2:
            themes.append(theme)
    return themes or ["payments", "cross_functional"]


def _build_tailoring_brief(job: Job) -> str:
    themes = _detect_themes(job.description)
    requirements = _extract_requirements(job.description)

    lines = [
        f"# Resume Tailoring Brief",
        f"**Role:** {job.title}",
        f"**Company:** {job.company}",
        f"**Job URL:** {job.url}",
        f"**Score:** {job.score}/100",
        f"**Location:** {job.location}",
        "",
        "---",
        "",
        "## Detected Job Themes",
        "",
    ]
    for t in themes:
        lines.append(f"- {t.replace('_', ' ').title()}")

    lines += ["", "## Key Requirements to Match", ""]
    if requirements:
        for req in requirements:
            lines.append(f"- {req}")
    else:
        lines.append("_(could not auto-extract — review job description manually)_")

    lines += ["", "## Recommended Bullet Points to Emphasize", ""]
    for theme in themes:
        highlights = _RESUME_HIGHLIGHTS.get(theme, [])
        if highlights:
            lines.append(f"### {theme.replace('_', ' ').title()}")
            for h in highlights:
                lines.append(f"- **Lead with:** {h}")
            lines.append("")

    lines += [
        "## Section Order Recommendation",
        "",
        "1. Summary ← **customize the headline to match the role's language**",
        "2. Experience (current role first — move most relevant bullets to top)",
        "3. Projects & Proof Points ← **reorder to match detected themes**",
        "4. Skills",
        "5. Education",
        "",
        "## Quick Keyword Insertions",
        "",
    ]
    # Suggest keywords the JD uses that aren't in the standard resume
    jd_keywords = set(re.findall(r"\b[a-z]{4,}\b", job.description.lower()))
    resume_standard = {"payment", "settlement", "ach", "api", "roadmap", "cross", "functional", "scale"}
    new_keywords = [kw for kw in sorted(jd_keywords) if kw not in resume_standard][:20]
    for kw in new_keywords:
        lines.append(f"- `{kw}`")

    lines += [
        "",
        "---",
        "_Generated by Job Search Automation — review before using._",
    ]
    return "\n".join(lines)


def _build_replacements_brief(job: Job, replacements: dict) -> str:
    """Render Claude's actual swaps as markdown for the no-GDocs local fallback,
    so the refinement-loop output is preserved instead of a keyword-only brief."""
    sections = []
    for key, label in (("summary", "Summary"), ("skills_core", "Skills (Core)"),
                       ("skills_domain", "Skills (Domain)")):
        entry = replacements.get(key)
        if isinstance(entry, dict) and entry.get("replacement"):
            sections.append(f"## {label}\n\n**Replace:**\n> {entry.get('original', '')}\n\n"
                            f"**With:**\n> {entry['replacement']}")
    for i, b in enumerate(replacements.get("bullets") or [], 1):
        if isinstance(b, dict) and b.get("replacement"):
            sections.append(f"## Bullet {i}\n\n**Replace:**\n> {b.get('original', '')}\n\n"
                            f"**With:**\n> {b['replacement']}")
    if not sections:
        return ""
    header = [
        f"# Tailored Resume Changes — {job.title} @ {job.company}",
        f"**Job URL:** {job.url}",
        f"**Score:** {job.score}/100",
        "",
        "_Apply these exact text swaps to your base resume._",
        "",
    ]
    alignment = replacements.get("alignment") or {}
    footer = []
    if alignment.get("differentiator"):
        footer += ["", f"**Differentiator:** {alignment['differentiator']}"]
    actions = replacements.get("action_items") or []
    if actions:
        footer += ["", "## Action Items Before Applying"] + [f"- {a}" for a in actions]
    return "\n".join(header) + "\n\n" + "\n\n".join(sections) + "\n".join(footer)


async def tailor_resume(job: Job, resume_text: str = "") -> str:
    """
    Produces a tailored resume Google Doc for the job:
      1. Calls Claude to generate exact text replacements (summary, bullets, skills)
         — or reuses cached replacements from a prior run whose GDoc step failed,
         so transient Google errors never re-spend Claude usage.
      2. Copies the base resume GDoc and applies the replacements surgically
         (fonts and layout stay intact — only the changed text is swapped).
      3. Returns the GDoc URL. Transient GDoc failures RAISE (job stays pending,
         retried next run); the local-file fallback is only for setups with no
         Google credentials at all.
    """
    from integrations.google_docs import create_tailored_doc
    from core.claude_client import ClaudeClient, require_claude

    # Claude is mandatory — abort loudly rather than emit a keyword-only brief
    require_claude()
    if not resume_text:
        raise RuntimeError(
            "No resume text loaded — check RESUME_GDOC_ID / Google credentials. "
            "Tailoring requires the base resume; refusing to emit a keyword-only brief."
        )

    # --- AI tailoring (Claude) — errors propagate and abort the run ---
    cache_path = os.path.join(_CACHE_DIR, f"{job.id}.json")
    replacements = None
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                replacements = json.load(f)
            print(f"    [tailor] Reusing cached replacements from a previous run (no Claude spend)")
        except Exception:
            replacements = None  # unreadable cache — regenerate
    if replacements is None:
        print(f"    [tailor] Generating replacements via Claude...")
        client = ClaudeClient(resume_text)
        replacements = await client.tailor_resume_for_job(job, resume_text)
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(replacements, f)
    n = len(replacements.get("bullets", [])) + (1 if replacements.get("summary") else 0)
    print(f"    [tailor] {n} targeted changes generated")

    # Post-modification ATS score — prefer the review panel's claimable-coverage
    # figure (driven to ≥90 by the refinement loop); fall back to raw alignment.
    panel_pct = replacements.get("_ats_claimable_pct")
    alignment = replacements.get("alignment") or {}
    matched = alignment.get("matched_keywords") or []
    missing = alignment.get("missing_keywords") or []
    if panel_pct:
        job.ats_post_score = f"{int(panel_pct)}%"
        print(f"    [tailor] ATS post-mod score (panel, claimable keywords): {job.ats_post_score}")
    elif matched or missing:
        job.ats_post_score = f"{round(100 * len(matched) / (len(matched) + len(missing)))}%"
        print(f"    [tailor] ATS post-mod score: {job.ats_post_score} ({len(matched)} matched / {len(missing)} missing)")

    # --- Create / update GDoc ---
    # Transient API failures raise: the job must stay pending (NOT get a dead
    # file:// link stored as done). The Claude output is cached above, so the
    # retry costs no Claude usage.
    try:
        gdoc_url = await create_tailored_doc(replacements, job, resume_text)
    except Exception as e:
        raise RuntimeError(
            f"GDoc creation failed for {job.company} ({e}). Claude output is cached "
            f"({os.path.basename(cache_path)}) — the job stays pending and the next "
            "run retries the GDoc without re-spending Claude."
        ) from e
    if gdoc_url:
        try:
            os.remove(cache_path)  # done — no longer pending
        except OSError:
            pass
        return gdoc_url

    # --- Local file fallback (only when GDocs is not configured at all) ---
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{job.company}_{job.title}")[:80]
    filepath = os.path.join(_OUTPUT_DIR, f"{safe_name}.md")
    brief = _build_replacements_brief(job, replacements) or _build_tailoring_brief(job)
    with open(filepath, "w") as f:
        f.write(brief)
    try:
        os.remove(cache_path)
    except OSError:
        pass
    return f"file://{os.path.abspath(filepath)}"
