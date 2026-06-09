"""
AI scoring client — uses Groq (Llama 3.3 70B) for job evaluation and resume tailoring.
Free tier: 14,400 requests/day, 30 RPM.

Scoring prompt returns JSON with:
  score (0-100), breakdown, match_reasons, gaps, tailoring suggestions
"""
import asyncio
import json
import os
import threading
import time
from collections import deque

import yaml

_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "profile.yml")
_MODEL = "llama-3.1-8b-instant"  # 500k tokens/day free vs 100k for 70B


class _RateLimiter:
    """Thread-safe rate limiter: max N calls per 60 seconds."""

    def __init__(self, max_per_minute: int = 25):  # conservative under 30 RPM free limit
        self._max = max_per_minute
        self._calls: deque = deque()
        self._lock = threading.Lock()

    def wait_if_needed(self) -> None:
        with self._lock:
            now = time.monotonic()
            while self._calls and now - self._calls[0] > 60.0:
                self._calls.popleft()
            if len(self._calls) >= self._max:
                sleep_for = 60.0 - (now - self._calls[0]) + 0.3
                if sleep_for > 0:
                    time.sleep(sleep_for)
            self._calls.append(time.monotonic())


class GeminiClient:
    """AI job scorer using Groq (Llama 3.3 70B). Named GeminiClient for API compat."""

    def __init__(self, resume_text: str):
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set in .env — get a free key at console.groq.com/keys")

        try:
            from groq import Groq
            self._client = Groq(api_key=api_key)
        except ImportError:
            raise RuntimeError("Run: pip install groq")

        self._resume = resume_text
        self._profile = self._load_profile()
        self._rate = _RateLimiter(max_per_minute=25)

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

TARGET LEVELS (only these are acceptable):
IC2/PM: Product Manager, Product Manager Growth, Product Manager Platform, Technical PM
IC3/Senior PM: Senior Product Manager, Senior PM, Sr. PM, Product Manager II, Product Manager 2, Senior Technical Product Manager

HARD RULES — apply before anything else:
- If title is Director / VP / Head of Product / Staff PM / Principal PM / Group PM → score ≤ 10 immediately (too senior)
- If title is Associate PM / Junior PM / APM / Coordinator → score ≤ 10 immediately (too junior)
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
        max_retries = 3
        for attempt in range(max_retries):
            self._rate.wait_if_needed()
            try:
                response = self._client.chat.completions.create(
                    model=_MODEL,
                    messages=[
                        {"role": "system", "content": self._system_prompt()},
                        {"role": "user", "content": self._user_prompt(job)},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=1000,
                )
                text = response.choices[0].message.content or ""
                return json.loads(text)
            except Exception as e:
                is_rate_limited = "429" in str(e) or "rate" in str(e).lower() or "quota" in str(e).lower()
                if is_rate_limited and attempt < max_retries - 1:
                    wait = 65 * (attempt + 1)
                    print(f"  [groq] rate limited — waiting {wait}s before retry {attempt + 2}/{max_retries}")
                    time.sleep(wait)
                    continue
                raise

    async def score_jobs_batch(self, jobs: list) -> list:
        """Score jobs sequentially to stay within the 25 RPM budget."""
        enriched = []
        total = len(jobs)
        for i, job in enumerate(jobs, 1):
            print(f"  [groq] scoring {i}/{total}: {job.company} / {job.title[:50]}")
            try:
                result = await asyncio.to_thread(self._call_sync, job)
                _apply_result(job, result)
            except Exception as e:
                print(f"  [groq] error — keeping keyword score: {e}")
            enriched.append(job)
        return enriched

    # ── Company vocabulary: deterministic signals injected before Groq runs ──────
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
        "jpmorgan": (
            "institutional payment rails, wholesale payments, treasury services, "
            "ISO 20022 migration, real-time payments, global clearing"
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
    }

    def _company_vocab(self, company: str) -> str:
        key = (company or "").strip().lower()
        for name, vocab in self._COMPANY_PROFILES.items():
            if name in key or key in name:
                return vocab
        return ""

    def _tailor_system_prompt(self) -> str:
        return """You are a senior talent partner at a top-tier fintech company. You have read this job description twenty times. You know exactly what separates a resume that gets a callback from one that gets filed.

Your job is surgical: find the minimum set of text swaps — no more than 5 — that will make this candidate's resume resonate with this specific company. Every word you add must come from either the candidate's resume or the job description. No filler. No generic PM language.

CANDIDATE GROUND TRUTH (never fabricate beyond these facts):
- 8 years at Intuit, Nium, Goldman Sachs
- $530B+ TPV platform (ACH, RTP, FedNow, Wires, Visa Direct)
- Cut instant-payment unit cost 72%, unlocked $8.2B real-time TPV
- Built FedNow via FedLine Direct (~40 national FedNow Certified Service Providers)
- Built Finsight: agentic ops console, anomaly detection from hours to <5 min
- Lifted account verification 17%, merchant conversion 3.1% via RTP micro-deposits
- Generated $8.5M ARR via Single-Use Virtual Cards
- Cross-border: Nium, RippleNet, $8.5M monthly TPV
- Stack: ACH, RTP, FedNow, ISO 20022, NACHA, ANSI X9, KYC, AML, PCI DSS

ABSOLUTE RULES:
1. Every "original" field must be a character-perfect verbatim substring copied from the resume — not paraphrased, not trimmed, not altered.
2. Every "replacement" must contain at least one verbatim phrase lifted directly from the jd_anchor field.
3. BANNED WORDS — never use these in any replacement, ever:
   results-driven, proven track record, passionate about, dynamic, self-starter, detail-oriented,
   team player, leveraged, spearheaded, synergized, innovative, transformative, robust, seamlessly,
   cutting-edge, best-in-class, world-class, game-changing, impactful, actionable, holistic,
   strategic thinker, thought leader, deep dive, circle back, move the needle, bandwidth,
   at the end of the day, it is worth noting, it is important to note, furthermore, moreover,
   in conclusion, in summary, as a result of, in order to, utilize (use "use" instead).
4. NO LONG HYPHENS (em dashes): do not use — in replacements. Use a comma, period, or colon instead.
5. SOUND HUMAN AND CONFIDENT: write the way a sharp senior PM would describe their own work in conversation.
   Direct. Specific. No hedging. No throat-clearing. Start bullets with strong past-tense action verbs
   (Built, Cut, Shipped, Lifted, Grew, Launched, Designed, Owned) — not "Responsible for" or "Helped with".
6. NO AI TELLS: if someone reads it and thinks "an AI wrote this", it fails. Read each replacement as if
   you are that PM describing their work at a dinner table. It must sound like a real person, not a document.
7. LENGTH IS STRICT: every replacement must be equal to or shorter in character count than the original.
   The resume must stay on one page.
8. Grammar must be flawless — no run-on sentences, no dangling modifiers, no awkward constructions.
9. Return exactly 1 summary change + up to 4 bullet or skills changes. No more than 5 total.
10. For every bullet replacement, include a "bold_phrases" list — exact substrings within the replacement
    to typographically bold: key metrics, dollar amounts, percentages, and the JD-anchor phrase. Max 4 per bullet.
11. Return ONLY valid JSON. No markdown fences. No explanation outside the JSON.
12. Include a "reorder_suggestion": identify which single existing bullet in the resume (not one you rewrote)
    should move to position #1 in its role section because it is the most JD-relevant proof point.
    Provide its first 8 words verbatim and one concise sentence explaining why it should lead.

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
  }}
}}"""

    def tailor_resume_sync(self, job, resume_text: str) -> dict:
        """
        Two-pass tailoring:
          Pass 1 (cheap): extract top JD signals and candidate match points.
          Pass 2 (main):  produce exact replacements anchored to JD phrases.
        Returns dict with keys: summary, bullets, skills_core, skills_domain.
        """
        # ── Pass 1: extract JD signals ────────────────────────────────────────
        self._rate.wait_if_needed()
        signal_response = self._client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": "You are a job analyst. Return only valid JSON, no markdown."},
                {"role": "user", "content": f"""Extract the 5 most important requirements from this job description.
For each, identify the strongest matching proof point from the candidate's resume.

JD: {(job.description or '')[:2000]}

CANDIDATE HIGHLIGHTS:
- $530B+ TPV platform: ACH, RTP, FedNow, Wires, Visa Direct
- FedNow FedLine Direct (one of ~40 national Certified Service Providers)
- 72% unit cost reduction, $8.2B real-time TPV unlocked
- Finsight agentic ops console: anomaly detection hours → <5 min
- Account verification +17%, merchant conversion +3.1% via RTP micro-deposits
- $8.5M ARR Single-Use Virtual Cards, $570M TPV, 1M+ users
- Cross-border: RippleNet, $8.5M monthly TPV, same-day settlement
- KYC, AML, OFAC, Reg E, PCI DSS, ISO 20022, NACHA, ANSI X9

Return JSON: {{"jd_signals": [{{"requirement": "...", "exact_jd_phrase": "...", "candidate_proof_point": "..."}}]}}"""},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=600,
        )
        try:
            signals = json.loads(signal_response.choices[0].message.content or "{}")
            jd_signals = signals.get("jd_signals", [])
        except Exception:
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

        # ── Pass 2: produce replacements anchored to extracted signals ─────────
        self._rate.wait_if_needed()
        response = self._client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": self._tailor_system_prompt()},
                {"role": "user", "content": self._tailor_prompt(job, resume_text) + signals_block},
            ],
            response_format={"type": "json_object"},
            temperature=0.15,
            max_tokens=2400,
        )
        text = response.choices[0].message.content or "{}"
        result = json.loads(text)

        # ── Post-parse: warn if jd_anchor not found in actual JD ─────────────
        jd_lower = (job.description or "").lower()
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

        return result

    async def tailor_resume_for_job(self, job, resume_text: str) -> dict:
        """Async wrapper for tailor_resume_sync."""
        return await asyncio.to_thread(self.tailor_resume_sync, job, resume_text)


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
        "source": "groq/llama-3.3-70b",
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


def is_gemini_available() -> bool:
    """Returns True if any AI scoring backend is configured."""
    return bool(os.environ.get("GROQ_API_KEY", ""))
