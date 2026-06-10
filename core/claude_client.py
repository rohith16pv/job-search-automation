"""
AI scoring client — uses Claude (via the `claude` CLI in headless mode) for job
evaluation and resume tailoring.

Runs on your Claude subscription: the CLI uses the login from `claude` / Claude
Code, so no API key or pay-per-token billing is needed. Override the model with
CLAUDE_MODEL in .env (default: claude-opus-4-8; use claude-haiku-4-5 to conserve
subscription limits on big scoring runs).

Scoring prompt returns JSON with:
  score (0-100), breakdown, match_reasons, gaps, tailoring suggestions
"""
import asyncio
import json
import os
import re
import shutil
import subprocess
import time

import yaml

_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "profile.yml")

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")
_CLI_TIMEOUT = 180  # seconds per call

# Tailoring refinement loop: after the initial swaps, a review panel (ATS
# parser + recruiter + hiring manager + essence guard) grades the result and
# drives revisions until the bar is met or rounds run out.
_TAILOR_REFINE_ROUNDS = int(os.environ.get("TAILOR_REFINE_ROUNDS", "2"))
_TAILOR_ATS_TARGET = int(os.environ.get("TAILOR_ATS_TARGET", "90"))

_LOGIN_HELP = (
    "Claude is required for scoring and tailoring — this pipeline does not fall back "
    "to keyword-only mode. Fix: open a terminal, run `claude`, and log in with your "
    "Claude subscription account, then re-run. (Install: https://claude.com/claude-code)"
)


class ClaudeUnavailableError(RuntimeError):
    """Raised when the claude CLI is missing or not authenticated. The pipeline
    aborts instead of silently degrading to keyword-only scoring."""


class ClaudeUsageLimitError(RuntimeError):
    """Raised when the Claude subscription usage limit is hit. The limit resets
    on a multi-hour window, so in-run retries are futile — callers should stop
    spending immediately, keep completed work published, and let the next run
    pick up the remainder."""


def require_claude() -> None:
    """Abort early with a clear message if the claude CLI is not installed."""
    if not is_claude_available():
        raise ClaudeUnavailableError(f"`claude` CLI not found on PATH. {_LOGIN_HELP}")


def _is_auth_error(text: str) -> bool:
    t = text.lower()
    return "authenticate" in t or "authentication" in t or "401" in t or "log in" in t


def _is_usage_limit(text: str) -> bool:
    """Subscription usage-limit messages from the claude CLI (e.g. 'Claude usage
    limit reached', '5-hour limit reached ∙ resets 3am'). Distinct from transient
    rate/529 errors, which short retries can ride out."""
    t = text.lower()
    return "usage limit" in t or "limit reached" in t or "out of extra usage" in t


def _extract_json(text: str) -> dict:
    """Parse a JSON object out of model output, tolerating markdown fences."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _clean_env() -> dict:
    """Child env for the claude CLI: drop ANTHROPIC_* overrides (e.g. a proxy
    ANTHROPIC_BASE_URL inherited when running inside a Claude Code session) so
    the CLI authenticates with the stored subscription login."""
    return {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}


def _claude_call(system_prompt: str, user_prompt: str, max_retries: int = 3) -> dict:
    """One-shot Claude call via `claude -p`. Returns the parsed JSON object."""
    cmd = [
        "claude", "-p",
        "--model", CLAUDE_MODEL,
        "--output-format", "json",
        "--system-prompt", system_prompt,
        "--tools", "",
    ]
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            proc = subprocess.run(
                cmd,
                input=user_prompt,
                capture_output=True,
                text=True,
                timeout=_CLI_TIMEOUT,
                env=_clean_env(),
            )
            envelope = json.loads(proc.stdout) if proc.stdout.strip() else {}
            if envelope.get("is_error"):
                detail = str(envelope.get("result"))[:300]
                if envelope.get("api_error_status") in (401, 403) or _is_auth_error(detail):
                    # Auth failures never fix themselves — abort the run, don't retry
                    raise ClaudeUnavailableError(f"claude CLI auth failed: {detail}. {_LOGIN_HELP}")
                if envelope.get("api_error_status") == 429 or _is_usage_limit(detail):
                    # Subscription limit — resets in hours, not seconds. Don't retry.
                    raise ClaudeUsageLimitError(
                        f"Claude usage limit hit: {detail}. Completed work is preserved — "
                        "re-run after the limit resets to pick up the remainder."
                    )
                raise RuntimeError(f"claude CLI error result: {detail}")
            if proc.returncode != 0:
                raise RuntimeError(f"claude CLI exited {proc.returncode}: {proc.stderr.strip()[:300]}")
            return _extract_json(envelope.get("result", ""))
        except (ClaudeUnavailableError, ClaudeUsageLimitError):
            raise
        except Exception as e:
            last_err = e
            is_rate_limited = "rate" in str(e).lower() or "limit" in str(e).lower() or "529" in str(e)
            if attempt < max_retries - 1:
                wait = (60 if is_rate_limited else 5) * (attempt + 1)
                print(f"  [claude] call failed ({str(e)[:120]}) — retrying in {wait}s ({attempt + 2}/{max_retries})")
                time.sleep(wait)
                continue
    raise last_err


class ClaudeClient:
    """AI job scorer + resume tailor backed by the Claude subscription (claude CLI)."""

    def __init__(self, resume_text: str):
        require_claude()
        self._resume = resume_text
        self._profile = self._load_profile()

    @staticmethod
    def _load_profile() -> dict:
        try:
            with open(_PROFILE_PATH) as f:
                return yaml.safe_load(f)
        except Exception:
            return {}

    def _system_prompt(self) -> str:
        p = self._profile
        cand = p.get("candidate", {})
        career = p.get("career", {})
        targeting = p.get("targeting", {})
        return f"""You are an expert recruiter and career coach evaluating job fits for:

Name: {cand.get('full_name', 'Rohith Purimetla Vinay')}
Current Title: {career.get('current_title', 'Senior Product Manager')}
Years Experience: {career.get('years_experience', 10)}
Industry Focus: {career.get('industry_focus', 'Payments, Fintech, Money Movement')}
Target Roles: {', '.join(targeting.get('target_roles', ['Senior PM', 'Senior Product Manager', 'Product Manager II', 'Technical PM']))}
Target Location: Anywhere in USA (strongly prefer Remote or Hybrid)
Domain Expertise: {', '.join(targeting.get('domain_keywords', [])[:8])}

Candidate Resume (summary):
{self._resume[:1500]}

SCORING GUIDE (0-100):
90-100 → Near-perfect match: right title, right domain, right level, clear resume hooks
70-89  → Strong match: apply with targeted resume tweaks
50-69  → Moderate match: worth tracking in P1 backlog
30-49  → Weak match: significant gaps or wrong level
0-29   → Poor fit: skip

TARGET LEVELS:
Sweet spot (score 70–100): Senior PM, Sr PM, PM II/2/III/3, Technical PM, Product Manager, bare "PM" — any IC3-level PM variant
Above level (cap at 65): Staff PM, Principal PM, Group PM, Lead PM, Product Lead — worth tracking in P1, not a hot lead
Too junior (score ≤ 10): Associate PM, APM, Junior PM, Entry Level PM, Coordinator
Too senior (score ≤ 10): Director, VP, SVP, EVP, Head of Product, CPO, Chief Product Officer

HARD RULES — apply before anything else:
- If title is Director / VP / SVP / EVP / Head of Product / CPO / Chief Product → score ≤ 10 immediately (too senior)
- If title is Staff PM / Principal PM / Group PM / Lead PM / Product Lead → cap score at 65 (above target level)
- If title is Associate PM / Junior PM / APM / Entry Level PM → score ≤ 10 immediately (too junior)
- If title contains Engineering / Sales / Marketing / Design / Analyst (non-PM) → score ≤ 10 immediately
- If no payments/fintech/financial services domain signal anywhere in JD → cap score at 45
- If role is outside USA and not remote-friendly → cap score at 30
- Score should reflect realistic probability of getting an interview, not just keyword overlap

Return ONLY valid JSON. No markdown fences, no explanation outside JSON."""

    def _user_prompt(self, job) -> str:
        desc = (job.description or "")[:1500]
        return f"""Evaluate this job:

Title: {job.title}
Company: {job.company}
Location: {job.location}
Source: {job.source}

Job Description:
{desc}

Return JSON with keys: score (int 0-100), title_fit (str), domain_fit (str),
skills_fit (str), seniority_fit (str), location_fit (str),
match_reasons (list of 2-4 strings), gaps (list of 1-3 strings),
tailoring (object with rewritten_summary, bullets_to_lead_with, keywords_to_weave_in,
section_order, new_bullets_to_add — only populate if score >= 50)."""

    def _call_sync(self, job) -> dict:
        return _claude_call(self._system_prompt(), self._user_prompt(job))

    async def score_jobs_batch(self, jobs: list) -> list:
        """Score jobs sequentially — each call is a full claude CLI invocation.
        Any failure aborts the run (no silent fallback to keyword scores)."""
        enriched = []
        total = len(jobs)
        for i, job in enumerate(jobs, 1):
            print(f"  [claude] scoring {i}/{total}: {job.company} / {job.title[:50]}")
            try:
                result = await asyncio.to_thread(self._call_sync, job)
            except (ClaudeUnavailableError, ClaudeUsageLimitError):
                raise  # systemic — keep the type so callers can stop cleanly
            except Exception as e:
                raise RuntimeError(
                    f"Claude scoring failed on job {i}/{total} ({job.company} / {job.title[:50]}): {e}"
                ) from e
            _apply_result(job, result)
            enriched.append(job)
        return enriched

    # ── Company vocabulary: deterministic signals injected before Claude runs ────
    _COMPANY_PROFILES = {
        "stripe": (
            "payment infrastructure, global payments network, financial infrastructure for the internet, "
            "API-first platform, developer-facing products, money movement primitives"
        ),
        "plaid": (
            "financial data network, open finance, consumer-permissioned data, bank connectivity, "
            "account verification, identity and fraud, developer platform"
        ),
        "coinbase": (
            "crypto economy, onchain financial system, self-custody, L2 networks, "
            "stablecoin infrastructure, regulated crypto exchange"
        ),
        "capital one": (
            "data-driven bank, machine learning at scale, real-time decisioning, "
            "digital-first banking, customer-facing mobile platform"
        ),
        "brex": (
            "spend management, corporate cards for startups, embedded finance, "
            "B2B payments, real-time spend controls, financial OS for businesses"
        ),
        "mercury": (
            "banking for startups, treasury management, API banking, "
            "business checking, cash flow visibility, founder-first banking"
        ),
        "ramp": (
            "corporate spend management, finance automation, real-time spend controls, "
            "accounts payable, vendor payments, treasury"
        ),
        "chime": (
            "consumer banking, earned wage access, fee-free banking, "
            "direct deposit, debit rails, financial inclusion"
        ),
        "affirm": (
            "buy now pay later, consumer credit, merchant checkout, "
            "underwriting at scale, adaptive checkout, BNPL network"
        ),
        "robinhood": (
            "retail investing, fractional shares, crypto trading, "
            "instant deposits, brokerage infrastructure, margin lending"
        ),
        "klarna": (
            "BNPL, flexible payments, checkout conversion, "
            "consumer credit, merchant integrations, shopping network"
        ),
        "adyen": (
            "unified commerce platform, acquiring, issuing, "
            "global payment acceptance, in-person and online, enterprise merchants"
        ),
        "visa": (
            "global payment network, Visa Direct, push payments, "
            "card-not-present, network tokenization, acceptance infrastructure"
        ),
        "mastercard": (
            "multi-rail strategy, real-time push payments, open banking, "
            "digital-first issuance, B2B cross-border flows"
        ),
        "paypal": (
            "two-sided payments network, branded checkout, BNPL, Venmo, "
            "merchant acceptance, digital wallet ecosystem"
        ),
        "square": (
            "seller ecosystem, omnichannel commerce, Cash App, "
            "financial services for SMBs, payments hardware, instant payouts"
        ),
        "fiserv": (
            "core banking, merchant acquiring, payment processing, "
            "Clover POS, financial institution technology, debit network"
        ),
        "marqeta": (
            "modern card issuing, just-in-time funding, "
            "virtual cards, spend controls, open API issuing platform"
        ),
        "wise": (
            "cross-border payments, multi-currency accounts, "
            "real exchange rate, international transfers, borderless banking"
        ),
        "nium": (
            "global payments infrastructure, multi-currency wallets, "
            "cross-border payouts, embedded finance APIs, bank-to-bank transfers"
        ),
        "jpmorgan": (
            "wholesale payments, treasury services, ISO 20022, real-time payments, "
            "global clearing, institutional payment rails, liquidity management"
        ),
        "citi": (
            "treasury and trade solutions, cross-border payments, supply chain finance, "
            "global transaction banking, FX, trade finance, institutional clients"
        ),
        "ripple": (
            "blockchain-based payments, RippleNet, cross-border settlement, "
            "ODL on-demand liquidity, CBDC, crypto-enabled money movement"
        ),
        "tipalti": (
            "global accounts payable, mass payouts, supplier payments, "
            "payment operations automation, multi-currency, tax compliance"
        ),
        "deel": (
            "global payroll, contractor payments, employer of record, "
            "cross-border compliance, international hiring, multi-currency payroll"
        ),
        "finix": (
            "payments infrastructure, payment facilitation, merchant acquiring, "
            "embedded payments, payment operations, ISV payments"
        ),
        "sardine": (
            "fraud prevention, device intelligence, behavior biometrics, "
            "AML, KYC, real-time risk signals, compliance automation"
        ),
        "highnote": (
            "modern card issuing, embedded finance, program management, "
            "virtual and physical cards, spend controls, BIN sponsorship"
        ),
        "cross river": (
            "banking-as-a-service, API banking, fintech lending, "
            "ACH, RTP, card issuing, regulatory compliance for fintechs"
        ),
        "orum": (
            "instant money movement, real-time payments, ACH optimization, "
            "payment routing intelligence, same-day settlement"
        ),
        "argyle": (
            "employment data, payroll connectivity, income verification, "
            "earned wage access, HRIS integrations, consumer-permissioned data"
        ),
    }

    def _company_vocab(self, company: str) -> str:
        key = (company or "").strip().lower()
        for name, vocab in self._COMPANY_PROFILES.items():
            if name in key or key in name:
                return vocab
        return ""

    def _tailor_system_prompt(self) -> str:
        return """You are an elite career strategist and executive recruiter who evaluates resumes the way a top recruiter in this candidate's target field (payments / fintech product) would. You have read this job description twenty times. You know exactly what separates a resume that gets a callback from one that gets filed.

THE MECHANISM (why the rules below are absolute): your output drives an automated find-and-replace on a real, formatted Google Doc. Each "original" is searched as an exact string; if it is not a character-perfect substring of the resume, that swap silently fails and the doc ships unchanged. The doc must stay one page, so a replacement can never be longer than its original.

Your job is surgical: the minimum set of text swaps — no more than 5 — that will make this candidate's resume resonate with this specific company. Every word you add must come from the candidate's resume, the ground truth below, or the job description. No filler. No generic PM language.

ONE-PAGE RESUME — WORD ECONOMY AND CONFIDENCE:
The candidate runs a strict one-page resume, so every word must earn its place. Before returning any
replacement, reread it and delete every word the meaning survives without: qualifiers (very, highly,
various, multiple), redundant pairs ("plan and execute"), and scene-setting wind-ups. Prefer the
shorter word ("use" not "utilize", "led" not "was responsible for leading"). A 9-word bullet that
lands a number beats a 15-word bullet that explains it.
Write with confidence: state outcomes as facts and own them. Never "helped", "contributed to",
"supported", "was involved in", "worked on", "assisted with" — the candidate built it, cut it,
shipped it, grew it. No hedging ("approximately" only where ground truth says ~), no softeners,
no justifying the result. Confident is specific and quiet: the number does the bragging, not adjectives.

CANDIDATE GROUND TRUTH (never fabricate or estimate beyond these facts):
- Senior Product Manager, 8 years at Intuit, Nium, Goldman Sachs
- Owns money movement on a $530B+ TPV multi-rail platform (ACH, RTP, FedNow, Wires, Visa Direct, cross-border)
- RARE CREDENTIAL 1 (FedNow): built FedNow in-house via FedLine Direct, one of ~40 national FedNow
  Certified Service Providers; cut instant-payment unit cost 72% ($0.25 to $0.07); unlocked $8.2B monthly real-time TPV
- CONDITIONAL CREDENTIAL (standards seat): ANSI X9 and Federal Reserve working groups — use ONLY when
  the JD signals compliance, risk, regulatory, standards, or core payments-infrastructure work. Do NOT
  include it by default in every summary; for growth, consumer, or general PM roles it spends scarce
  characters without moving the recruiter.
- RARE CREDENTIAL 2 (production agentic AI): shipped Finsight, production agentic-AI ops console detecting
  payment anomalies across 7 rails, hours to <5 min. Always "shipped"/"production", never "piloted".
- Growth/P&L proof: $8.5M ARR via Single-Use Virtual Cards (interchange on $570M TPV, 1M+ users)
- Cross-border proof: Nium, RippleNet settlement cut from 3 days to same-day, $8.5M monthly TPV
- Consumer/activation proof: RTP micro-deposits lifted account verification 17%, merchant conversion 3.1%
- Stack: ACH, RTP, FedNow, ISO 20022, NACHA, ANSI X9, KYC, AML, OFAC, Reg E, PCI DSS

SUMMARY REPLACEMENT — build to this priority order (hard cap: not one character longer than the original summary; recruiters scan it for ~6 seconds):
1. Open with the JD's exact target title + scale, in the JD's vocabulary. Reorder so the JD's
   top-priority domain appears first.
2. The two RARE CREDENTIALS (FedNow, production agentic AI) are non-negotiable in every summary, with
   their numbers. Reframe the framing per JD (infra role: "made the build-vs-buy call to build FedNow
   in-house"; AI-forward role: lead with the agentic-AI credential), but the credential and its number
   always survive. Add the ANSI X9 / Federal Reserve seat ONLY when the JD is compliance-, risk-,
   regulatory-, standards-, or infrastructure-heavy — never by default.
3. Close with the flex fact matched to the JD's commercial goal:
   growth/P&L JD → $8.5M ARR on $570M TPV | cross-border/crypto JD → RippleNet 3 days to same-day
   | consumer/activation JD → verification +17% via RTP micro-deposits.
4. If over budget: cut adjectives and generic phrases first, then the ANSI X9 seat (if present), then
   shorten the flex fact, then compress scale stats. NEVER cut the two rare credentials or their numbers.
Final summary check: every sentence carries a number; the JD's top keywords appear; at least two
claims no other candidate can match.

BULLET REPLACEMENTS — use the XYZ formula: accomplished [X], as measured by [Y], by doing [Z].
Tie every bullet to a financial, operational, or user metric from ground truth. Frame around
ownership and leverage. No two replacements may start with the same verb.

ABSOLUTE RULES:
1. Every "original" field must be a character-perfect verbatim substring copied from the resume — not paraphrased, not trimmed, not altered, whitespace and punctuation identical.
2. Every "replacement" must contain at least one verbatim phrase lifted directly from the jd_anchor field. Mirror the JD's exact keyword phrasing — do not paraphrase keywords (ATS matches exact terms).
3. BANNED WORDS AND PATTERNS — never use these in any replacement, ever:
   results-driven, proven track record, passionate about, dynamic, self-starter, detail-oriented,
   team player, leveraged, spearheaded, synergized, fostered, pioneered, revolutionized, testament,
   delighted, innovative, transformative, robust, seamlessly, cutting-edge, best-in-class, world-class,
   game-changing, impactful, actionable, holistic, strategic thinker, thought leader, deep dive,
   circle back, move the needle, bandwidth, at the end of the day, it is worth noting, it is important
   to note, furthermore, moreover, in conclusion, in summary, as a result of, in order to,
   utilize (use "use"), filler adverbs (successfully, effectively, efficiently), passive voice,
   buzzword stacking.
4. NO LONG HYPHENS: no em dashes or en dashes anywhere in replacements. Use a comma, period, or colon.
5. SOUND HUMAN AND CONFIDENT: write the way a sharp senior PM would describe their own work in conversation.
   Direct. Specific. No hedging. No throat-clearing. Start bullets with crisp high-impact past-tense verbs
   (Built, Cut, Shipped, Lifted, Grew, Launched, Architected, Overhauled, Captured, Reduced, Owned) —
   not "Responsible for" or "Helped with". Let the metrics do the talking.
6. NO AI TELLS: if someone reads it and thinks "an AI wrote this", it fails. Read each replacement as if
   you are that PM describing their work at a dinner table. It must sound like a real person, not a document.
7. LENGTH IS STRICT: every replacement must be equal to or shorter in character count than the original.
   The resume must stay on one page.
8. Grammar must be flawless — no run-on sentences, no dangling modifiers, no awkward constructions.
9. Return exactly 1 summary change + up to 4 bullet or skills changes. No more than 5 total.
10. For every bullet replacement, include a "bold_phrases" list — exact substrings within the replacement
    to typographically bold so they survive a 6-second scan: key metrics, dollar amounts, percentages,
    and JD keywords. Max 4 per bullet.
11. Return ONLY valid JSON. No markdown fences. No explanation outside the JSON.
12. Include a "reorder_suggestion": identify which single existing bullet in the resume (not one you rewrote)
    should move to position #1 in its role section because it is the most JD-relevant proof point.
    Provide its first 8 words verbatim and one concise sentence explaining why it should lead.
13. NEVER fabricate or estimate a metric. If a stronger swap would need a number the ground truth does not
    provide, leave that swap out and add what's needed to "action_items" instead (e.g. "Dig up the latency
    SLA number for the FedNow launch — the JD asks for reliability metrics").
14. Include an "alignment" object: matched_keywords (JD keywords now present in the resume after your swaps),
    missing_keywords (JD must-haves the resume still cannot honestly claim), and differentiator (one sentence:
    the single strength this resume now leads with that other candidates cannot match). Report concrete
    keyword coverage — never invent numeric "ATS scores".

INTERNAL REVIEW (do this silently before returning; do not show this work):
a. SUBSTRING pass: re-check character-by-character that every "original" appears verbatim in the resume text.
b. ATS pass: the JD's top keywords appear in exact phrasing across your replacements.
c. RECRUITER pass: would the new summary survive a 6-second scan; do the two rare credentials (FedNow,
   agentic AI) and their numbers appear; is the ANSI X9 seat present only if the JD justifies it?
d. EDITOR pass: lengths within budget, banned words absent, no em/en dashes, no fabricated numbers,
   no two replacements starting with the same verb.
Fix any violation, then return only the JSON.

== FEW-SHOT: WHAT GOOD VS BAD TAILORING LOOKS LIKE ==
(Fictional company "Apex Payments" — do not use for any real target)

JD phrases: "Build and scale real-time payment rails for enterprise merchants" | "developer-facing API products for high-volume B2B clients"

BAD (do NOT do this):
  "Results-driven Senior PM with 8 years of experience driving mission-critical payments, demonstrating
   a proven track record of delivering scalable and secure solutions that move the needle."
  WHY WRONG: banned filler everywhere; JD phrase never appears; reads like a LinkedIn bot wrote it.

ALSO BAD (do NOT do this — em dash + AI phrasing):
  "Senior PM with 8 years building payments infrastructure — a track record of impactful, innovative
   solutions across Intuit, Nium, and Goldman Sachs."
  WHY WRONG: em dash used; "impactful", "innovative" are banned; no JD phrase appears.

GOOD (do this):
  "Senior Product Manager with 8 years scaling real-time payment rails for enterprise merchants, covering
   ACH, RTP, FedNow, and Wires at Intuit, Nium, and Goldman Sachs."
  WHY RIGHT: JD phrase verbatim; no em dashes; no banned words; sounds like a person wrote it; same length.

BAD skills (do NOT do this):
  replacement: "Product: Product analytics, platform strategy, A/B experimentation"
  WHY WRONG: lowercased the original; zero JD signal.

GOOD skills (do this):
  replacement: "Product: API Platform Strategy, B2B Product Analytics (Amplitude, SQL, Databricks), Developer-Facing Product Design, A/B Experimentation"
  WHY RIGHT: JD terms woven in naturally; reads like a real skills list, not AI output."""

    def _tailor_prompt(self, job, resume_text: str) -> str:
        company_vocab = self._company_vocab(job.company)
        vocab_block = (
            f"\nKNOWN VOCABULARY FOR {(job.company or '').upper()} — weave these phrases into replacements where they fit naturally:\n{company_vocab}\n"
            if company_vocab else ""
        )
        return f"""TARGET ROLE: {job.title} at {job.company} ({job.location})
{vocab_block}
FULL JOB DESCRIPTION:
---
{(job.description or '')[:3000]}
---

CANDIDATE RESUME (verbatim — all "original" fields must be exact substrings of this text):
---
{resume_text}
---

TASK: Identify the 5 highest-impact text replacements (1 summary + up to 4 bullets/skills).
For each change, identify the exact JD phrase that motivates it (jd_anchor).

Return this exact JSON structure:
{{
  "summary": {{
    "original": "<verbatim substring from resume>",
    "jd_anchor": "<exact phrase from JD that this change addresses>",
    "replacement": "<rewritten text — equal or shorter length, perfect grammar, jd_anchor phrase woven in verbatim>"
  }},
  "bullets": [
    {{
      "original": "<verbatim bullet from resume>",
      "jd_anchor": "<exact JD phrase>",
      "replacement": "<rewritten bullet — equal or shorter length, perfect grammar, jd_anchor phrase woven in verbatim>",
      "bold_phrases": ["<exact substring of replacement to bold — key metric, dollar amount, % or JD-anchor phrase>"]
    }}
  ],
  "skills_core": {{
    "original": "<verbatim skills line from resume>",
    "jd_anchor": "<exact JD phrase>",
    "replacement": "<reordered skills — equal or shorter, jd_anchor terms woven in, keep heading 'Product:' intact>"
  }},
  "skills_domain": {{
    "original": "<verbatim domain skills line from resume>",
    "jd_anchor": "<exact JD phrase>",
    "replacement": "<reordered domain skills — equal or shorter, jd_anchor terms woven in, keep heading 'Domain:' intact>"
  }},
  "reorder_suggestion": {{
    "bullet_fragment": "<first 8 words verbatim from the existing resume bullet that should move to #1 in its role>",
    "reason": "<one sentence: why this bullet should lead for this specific JD>"
  }},
  "alignment": {{
    "matched_keywords": ["<JD keywords now present in the resume after the swaps>"],
    "missing_keywords": ["<JD must-haves the resume still cannot honestly claim>"],
    "differentiator": "<one sentence: the strength this resume now leads with that others cannot match>"
  }},
  "action_items": ["<metric to dig up or gap to bridge before applying — empty list if none>"]
}}"""

    def _review_system_prompt(self) -> str:
        return """You are a three-person interview panel reviewing a tailored resume BEFORE it ships, plus an essence guard:

1. ATS PARSER — exact-match keyword scan against the JD. Keywords match only in the JD's exact phrasing.
2. RECRUITER — the 6-second scan: does this read as a highly confident, strong, obviously-qualified candidate for THIS specific role? Numbers visible, no hedging, no AI voice.
3. HIRING MANAGER (payments domain leader) — depth check: does the evidence convince someone who has shipped payment systems? Specific rails, real metrics, credible ownership.
4. ESSENCE GUARD — the tailored resume must still be the SAME person and voice as the base resume. Surgical swaps, not a rewrite. Penalize: generic AI phrasing, lost specificity, removed credentials or numbers, anything the base resume's author wouldn't say.

Be harsh and concrete — a soft review here means a rejection later. Never suggest fabricating anything. Return ONLY valid JSON, no markdown fences."""

    def _review_prompt(self, job, resume_text: str, result: dict) -> str:
        swaps = {
            k: {"original": e.get("original"), "replacement": e.get("replacement")}
            for k, e in _swap_entries(result)
        }
        return f"""ROLE: {job.title} at {job.company}

JOB DESCRIPTION:
---
{(job.description or '')[:2500]}
---

BASE RESUME (the swaps below replace exact substrings of this):
---
{resume_text[:3500]}
---

PROPOSED SWAPS:
{json.dumps(swaps, indent=1)[:3000]}

Evaluate the RESULTING resume (base resume with swaps applied):

1. ATS: list JD keywords present after the swaps (matched). Split missing keywords into:
   - claimable_missing: the candidate's record honestly supports them, the swaps just failed to weave them in
   - honest_gaps: the candidate cannot truthfully claim them (NEVER suggest adding these)
   coverage_pct = round(100 * matched / (matched + claimable_missing)) — integer.
2. RECRUITER: verdict "strong" or "weak", with concrete issues.
3. HIRING MANAGER: verdict "strong" or "weak", with concrete issues.
4. ESSENCE: preserved true/false, with issues (voice drift, lost facts, over-rewriting).
5. fixes: up to 5 SPECIFIC revision instructions that would push coverage_pct to ≥{_TAILOR_ATS_TARGET}
   and make both verdicts strong — without fabricating, without touching honest_gaps, and within
   the existing limits (max 5 swaps, each replacement ≤ its original's length, verbatim originals).

Return JSON:
{{"ats": {{"matched": [], "claimable_missing": [], "honest_gaps": [], "coverage_pct": 0}},
 "recruiter": {{"verdict": "", "issues": []}},
 "hiring_manager": {{"verdict": "", "issues": []}},
 "essence": {{"preserved": true, "issues": []}},
 "fixes": []}}"""

    def tailor_resume_sync(self, job, resume_text: str) -> dict:
        """
        Two-pass tailoring:
          Pass 1 (cheap): extract top JD signals and candidate match points.
          Pass 2 (main):  produce exact replacements anchored to JD phrases.
        Returns dict with keys: summary, bullets, skills_core, skills_domain.
        """
        # ── Pass 1: deep JD analysis ──────────────────────────────────────────
        try:
            signals = _claude_call(
                "You are a job analyst working for an executive recruiter. Return only valid JSON, no markdown.",
                f"""Analyze this job description for a resume-tailoring pass.

JD: {(job.description or '')[:2000]}

CANDIDATE HIGHLIGHTS:
- $530B+ TPV platform: ACH, RTP, FedNow, Wires, Visa Direct
- FedNow built in-house via FedLine Direct (one of ~40 national Certified Service Providers)
- 72% unit cost reduction ($0.25 to $0.07), $8.2B monthly real-time TPV unlocked
- ANSI X9 and Federal Reserve working groups seat
- Finsight production agentic-AI ops console: anomaly detection across 7 rails, hours → <5 min
- Account verification +17%, merchant conversion +3.1% via RTP micro-deposits
- $8.5M ARR Single-Use Virtual Cards (interchange on $570M TPV, 1M+ users)
- Cross-border: Nium, RippleNet, $8.5M monthly TPV, settlement 3 days → same-day
- KYC, AML, OFAC, Reg E, PCI DSS, ISO 20022, NACHA, ANSI X9

Extract:
1. jd_signals: the 5 most important requirements; for each, the exact JD phrase and the strongest
   matching candidate proof point.
2. keywords: the top 10 hard skills, tools, and role-specific terms in the JD's EXACT phrasing
   (these feed ATS matching — do not paraphrase).
3. scale_signals: one line on team size, user counts, growth stage, 0-to-1 vs scale-up.
4. commercial_goal: the business outcome this hire exists to drive, as one of:
   "growth/P&L" | "cross-border/crypto" | "consumer/activation" | "reliability/infra" | "compliance/risk"
   plus a short justification.

Return JSON: {{"jd_signals": [{{"requirement": "...", "exact_jd_phrase": "...", "candidate_proof_point": "..."}}],
"keywords": ["..."], "scale_signals": "...", "commercial_goal": {{"category": "...", "why": "..."}}}}""",
            )
            jd_signals = signals.get("jd_signals", [])
        except Exception:
            signals = {}
            jd_signals = []

        signals_block = ""
        if jd_signals:
            signals_block = "\n\nJD SIGNAL EXTRACTION (use these as jd_anchor values):\n"
            for s in jd_signals[:5]:
                signals_block += (
                    f"  • Requirement: {s.get('requirement','')}\n"
                    f"    Exact JD phrase: {s.get('exact_jd_phrase','')}\n"
                    f"    Candidate proof: {s.get('candidate_proof_point','')}\n"
                )
        if signals.get("keywords"):
            signals_block += f"\nJD KEYWORDS (exact phrasing, weave into replacements): {', '.join(signals['keywords'][:10])}\n"
        if signals.get("scale_signals"):
            signals_block += f"SCALE SIGNALS: {signals['scale_signals']}\n"
        goal = signals.get("commercial_goal") or {}
        if isinstance(goal, dict) and goal.get("category"):
            signals_block += (
                f"COMMERCIAL GOAL: {goal.get('category')} ({goal.get('why','')}) — "
                f"pick the summary flex fact and bullet emphasis to serve this goal.\n"
            )

        # ── Pass 2: produce replacements anchored to extracted signals ─────────
        result = _claude_call(
            self._tailor_system_prompt(),
            self._tailor_prompt(job, resume_text) + signals_block,
        )

        # ── Validate: every "original" must be a verbatim substring, else the
        #    GDoc replaceAllText silently no-ops. Retry once with corrections. ──
        bad = _invalid_originals(result, resume_text)
        if bad:
            print(f"    [tailor] {len(bad)} swap(s) failed verbatim check — retrying with corrections")
            correction = (
                "\n\nCORRECTION REQUIRED: in your previous attempt these \"original\" values were NOT "
                "character-perfect substrings of the resume (the find-and-replace would silently fail):\n"
                + "\n".join(f'  - {key}: "{orig[:120]}"' for key, orig in bad)
                + "\nRe-copy each original EXACTLY from the resume text (watch whitespace, punctuation, "
                "casing) and return the complete corrected JSON."
            )
            result = _claude_call(
                self._tailor_system_prompt(),
                self._tailor_prompt(job, resume_text) + signals_block + correction,
            )
            still_bad = _invalid_originals(result, resume_text)
            if still_bad:
                _drop_invalid(result, still_bad)
                print("    [tailor] ⚠ dropped swaps that still failed the verbatim check:")
                for key, orig in still_bad:
                    print(f"      - {key}: \"{orig[:100]}\"")

        if not _count_swaps(result):
            raise RuntimeError(
                f"Tailoring for {job.company} produced no valid swaps — every 'original' failed the "
                "verbatim-substring check. The GDoc would be an untouched copy; aborting instead."
            )

        # Soft check: replacements should not exceed original length (one-page constraint)
        for key, entry in _swap_entries(result):
            orig, repl = entry.get("original") or "", entry.get("replacement") or ""
            if orig and repl and len(repl) > len(orig):
                print(f"    [tailor] ⚠ {key} replacement is {len(repl) - len(orig)} chars longer than original — may push layout")

        # ── Agentic refinement loop: panel review → targeted revision ────────
        # Bar: ATS (claimable) coverage ≥ target, recruiter AND hiring-manager
        # verdicts "strong", essence preserved. Best round wins if bar not met.
        best, best_cov = result, -1
        for round_i in range(1, _TAILOR_REFINE_ROUNDS + 2):  # review rounds = refine rounds + 1
            try:
                review = _claude_call(
                    self._review_system_prompt(),
                    self._review_prompt(job, resume_text, result),
                )
            except Exception as e:
                print(f"    [tailor] review round {round_i} failed ({str(e)[:100]}) — keeping current swaps")
                break

            ats = review.get("ats") or {}
            cov = int(ats.get("coverage_pct") or 0)
            rec = (review.get("recruiter") or {}).get("verdict", "weak")
            hm = (review.get("hiring_manager") or {}).get("verdict", "weak")
            essence = review.get("essence") or {}
            essence_ok = bool(essence.get("preserved", True))
            print(f"    [tailor] panel round {round_i}: ATS {cov}% | recruiter {rec} | "
                  f"hiring-manager {hm} | essence {'preserved' if essence_ok else 'DRIFTED'}")

            result["_ats_claimable_pct"] = cov
            gaps = ats.get("honest_gaps") or []
            if gaps:
                items = result.setdefault("action_items", [])
                for g in gaps:
                    note = f"Honest gap vs JD (do not fake — prep an interview answer): {g}"
                    if note not in items:
                        items.append(note)

            if cov >= best_cov:
                best, best_cov = result, cov
            if cov >= _TAILOR_ATS_TARGET and rec == "strong" and hm == "strong" and essence_ok:
                print(f"    [tailor] ✅ bar met (ATS ≥ {_TAILOR_ATS_TARGET}, both verdicts strong, essence intact)")
                break
            if round_i > _TAILOR_REFINE_ROUNDS:
                print(f"    [tailor] refinement rounds exhausted — shipping best round (ATS {best_cov}%)")
                break

            fixes = review.get("fixes") or []
            issue_summary = "; ".join(
                (essence.get("issues") or []) +
                ((review.get("recruiter") or {}).get("issues") or [])[:2] +
                ((review.get("hiring_manager") or {}).get("issues") or [])[:2]
            )[:600]
            current_swaps = {k: {"original": e.get("original"), "replacement": e.get("replacement")}
                             for k, e in _swap_entries(result)}
            revision_block = (
                f"\n\nREVISION ROUND {round_i}: a review panel evaluated your previous swaps.\n"
                f"PREVIOUS SWAPS: {json.dumps(current_swaps)[:2500]}\n"
                f"PANEL: ATS claimable coverage {cov}% (target ≥{_TAILOR_ATS_TARGET}), recruiter {rec}, "
                f"hiring manager {hm}, essence {'preserved' if essence_ok else 'DRIFTED — pull back toward the base resume voice'}.\n"
                f"CLAIMABLE KEYWORDS STILL MISSING (weave these in): {json.dumps(ats.get('claimable_missing') or [])[:500]}\n"
                f"DO-NOT-CHASE (honest gaps — never add): {json.dumps(gaps)[:300]}\n"
                f"PANEL ISSUES: {issue_summary}\n"
                f"FIXES REQUIRED:\n" + "\n".join(f"- {f}" for f in fixes[:5]) +
                "\nProduce the COMPLETE corrected JSON (all swaps, not a diff). All absolute rules still "
                "apply: character-perfect verbatim originals, replacements ≤ original length, max 5 swaps, "
                "no fabrication, keep the candidate's own voice."
            )
            try:
                revised = _claude_call(
                    self._tailor_system_prompt(),
                    self._tailor_prompt(job, resume_text) + signals_block + revision_block,
                )
            except Exception as e:
                print(f"    [tailor] revision round {round_i} failed ({str(e)[:100]}) — keeping current swaps")
                break
            if _drop_bad_swaps(revised, resume_text):
                result = revised
            else:
                print(f"    [tailor] revision round {round_i} produced no valid swaps — keeping current")
                break

        result = best

        # Essence metric: how much of the base resume actually changed
        changed = sum(len(e.get("original") or "") for _, e in _swap_entries(result))
        pct_changed = 100 * changed / max(len(resume_text), 1)
        print(f"    [tailor] essence: {pct_changed:.0f}% of base resume text touched "
              f"({_count_swaps(result)} surgical swaps — the rest is verbatim your resume)")

        # ── Post-parse: warn if jd_anchor not found in actual JD ─────────────
        # (whitespace-normalized so line breaks in the JD don't trigger false alarms)
        jd_lower = " ".join((job.description or "").lower().split())
        for key in ("summary", "skills_core", "skills_domain"):
            entry = result.get(key)
            if not isinstance(entry, dict):
                continue
            anchor = " ".join((entry.get("jd_anchor") or "").lower().split()[:5])
            if anchor and anchor not in jd_lower:
                print(f"    [tailor] note: anchor not found in JD for '{key}': {anchor!r}")

        for i, b in enumerate(result.get("bullets") or []):
            if not isinstance(b, dict):
                continue
            anchor = " ".join((b.get("jd_anchor") or "").lower().split()[:5])
            if anchor and anchor not in jd_lower:
                print(f"    [tailor] note: anchor not found in JD for bullet[{i}]: {anchor!r}")

        # ── Report: alignment + action items for the user ─────────────────────
        alignment = result.get("alignment") or {}
        if isinstance(alignment, dict) and alignment:
            matched = alignment.get("matched_keywords") or []
            missing = alignment.get("missing_keywords") or []
            if matched:
                print(f"    [tailor] keywords matched : {', '.join(str(k) for k in matched[:10])}")
            if missing:
                print(f"    [tailor] keywords MISSING : {', '.join(str(k) for k in missing[:10])}")
            if alignment.get("differentiator"):
                print(f"    [tailor] differentiator   : {alignment['differentiator']}")
        actions = result.get("action_items") or []
        if actions:
            print(f"    [tailor] 📋 ACTION ITEMS before applying to {job.company}:")
            for a in actions:
                print(f"      • {a}")

        return result

    async def tailor_resume_for_job(self, job, resume_text: str) -> dict:
        """Async wrapper for tailor_resume_sync."""
        return await asyncio.to_thread(self.tailor_resume_sync, job, resume_text)


def _swap_entries(result: dict):
    """Yield (key, entry) for every replacement entry in a tailoring result."""
    for key in ("summary", "skills_core", "skills_domain"):
        entry = result.get(key)
        if isinstance(entry, dict):
            yield key, entry
    for i, b in enumerate(result.get("bullets") or []):
        if isinstance(b, dict):
            yield f"bullets[{i}]", b


def _invalid_originals(result: dict, resume_text: str) -> list:
    """Return [(key, original)] for swaps whose 'original' is not a verbatim
    substring of the resume — those would silently no-op in the GDoc."""
    bad = []
    for key, entry in _swap_entries(result):
        orig = (entry.get("original") or "").strip()
        if orig and orig not in resume_text:
            bad.append((key, orig))
    return bad


def _drop_invalid(result: dict, bad: list) -> None:
    """Remove swaps that failed the verbatim check so valid ones still apply."""
    bad_keys = {key for key, _ in bad}
    for key in ("summary", "skills_core", "skills_domain"):
        if key in bad_keys:
            result[key] = None
    if any(k.startswith("bullets[") for k in bad_keys):
        bad_idx = {int(k[8:-1]) for k in bad_keys if k.startswith("bullets[")}
        result["bullets"] = [
            b for i, b in enumerate(result.get("bullets") or []) if i not in bad_idx
        ]


def _drop_bad_swaps(result: dict, resume_text: str) -> int:
    """Drop swaps whose originals fail the verbatim check; return remaining count."""
    bad = _invalid_originals(result, resume_text)
    if bad:
        _drop_invalid(result, bad)
        for key, orig in bad:
            print(f"    [tailor] ⚠ dropped {key} (failed verbatim check): \"{orig[:80]}\"")
    return _count_swaps(result)


def _count_swaps(result: dict) -> int:
    """Number of applicable swaps (entries with both original and replacement)."""
    return sum(
        1 for _, e in _swap_entries(result)
        if (e.get("original") or "").strip() and (e.get("replacement") or "").strip()
    )


def _apply_result(job, result: dict) -> None:
    job.score = max(0, min(100, int(result.get("score", job.score))))
    job.score_breakdown = {
        "title": result.get("title_fit", ""),
        "domain": result.get("domain_fit", ""),
        "skills": result.get("skills_fit", ""),
        "seniority": result.get("seniority_fit", ""),
        "location": result.get("location_fit", ""),
        "match_reasons": result.get("match_reasons", []),
        "gaps": result.get("gaps", []),
        "source": f"claude/{CLAUDE_MODEL}",
    }
    tailoring = result.get("tailoring") or {}
    if tailoring:
        job.tailoring_notes = _format_tailoring(tailoring)


def _safe(v) -> str:
    """Coerce any AI response value to a plain string."""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v) if v is not None else ""


def _format_tailoring(t: dict) -> str:
    lines = ["## AI Tailoring Suggestions", ""]
    if t.get("rewritten_summary"):
        lines += ["### Rewritten Summary", _safe(t["rewritten_summary"]), ""]
    if t.get("bullets_to_lead_with"):
        items = t["bullets_to_lead_with"] if isinstance(t["bullets_to_lead_with"], list) else [t["bullets_to_lead_with"]]
        lines += ["### Lead With These Bullets"] + [f"- {_safe(b)}" for b in items] + [""]
    if t.get("new_bullets_to_add"):
        items = t["new_bullets_to_add"] if isinstance(t["new_bullets_to_add"], list) else [t["new_bullets_to_add"]]
        lines += ["### Add These New Bullets"] + [f"- {_safe(b)}" for b in items] + [""]
    if t.get("keywords_to_weave_in"):
        items = t["keywords_to_weave_in"] if isinstance(t["keywords_to_weave_in"], list) else [t["keywords_to_weave_in"]]
        lines += ["### Keywords to Weave In"] + [f"`{_safe(k)}`" for k in items] + [""]
    if t.get("section_order"):
        lines += ["### Section Order", _safe(t["section_order"]), ""]
    return "\n".join(lines)


def is_claude_available() -> bool:
    """Returns True if the claude CLI is installed (subscription auth)."""
    return shutil.which("claude") is not None
