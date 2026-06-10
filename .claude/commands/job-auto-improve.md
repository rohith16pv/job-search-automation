Run the improvement loop on demand: full health check + Claude self-review, then FIX what's broken and verify the fixes live. This is the burn-in follow-up packaged as a standalone command — no scan, no Sheets writes, no Claude scoring spend beyond the review itself.

## Steps — execute in order

### 1. Baseline
1. `cd /Users/rohith/Downloads/Github/job-search-automation`
2. Run `python3 scripts/health_check.py --review` — preflight (Claude/Sheets/Apify/run-gap), ATS slug audit of every configured board, last scout counts, and a forced Claude self-review (appends to `data/improvement_suggestions.md`).
3. Run `python3 scripts/scout_sweep.py` — live per-source job counts (free sources only; safe, writes nothing).

### 2. Diagnose
Build the issue list from three inputs:
- Health check warnings (dead boards, auth failures, stale runs)
- Sweep anomalies (source at 0 or far below its `data/health_history.json` baseline; `apple_jobs`/`wellfound` at 0 is expected — they're documented as scrape-blocked)
- The NEWEST section of `data/improvement_suggestions.md` (false-negative titles, scoring/query/source suggestions)

### 3. Fix — auto-apply the safe class, verify each fix live
Safe to fix without asking (do it now, in this session):
- **Dead ATS board**: probe where the company moved using `core.improve._probe_board` with `_slug_candidates(company)` variants; repoint the slug in `config/job_sources.yml` to the live board, or remove it (leaving a comment) if no public board exists — search queries then cover that company.
- **Broken scout endpoint** (HTTP 404/4xx from a previously working source): inspect the API/HTML live with small probes, fix the scout module, re-run `scripts/scout_sweep.py` and confirm the count recovered.
- **Config rot**: duplicate slugs, companies listed under the wrong ATS, entries the audit proves dead.

Needs user approval — propose in chat as concrete diffs with one-line rationale each, apply only what's approved:
- Scoring changes (`config/scoring.yml` keywords, blockers, thresholds)
- New or changed LinkedIn/Indeed queries (`config/job_sources.yml`)
- Routing threshold moves, new company additions beyond auto-discovery

### 4. Verify
- Re-run `python3 scripts/health_check.py` — must end `✅ ALL HEALTHY` (or every remaining ⚠ is explained in the summary).
- Re-run `python3 scripts/scout_sweep.py` if any scout code/config changed — counts must be ≥ pre-fix baseline.
- `python3 -m py_compile` any Python file touched.

### 5. Report
Summarize in chat:
- What was auto-fixed (before → after counts where relevant)
- Proposals awaiting approval (numbered, so the user can reply "apply 1 and 3")
- Anything deferred and why

## Error reporting
If ANY check fails or warns, highlight it prominently in a dedicated "⚠ Issues" section — quote the exact line, what it means, what was done about it (or what the user must decide). If the run is fully healthy and nothing needed fixing, say exactly that in two sentences — no padding.

## Notes
- Costs: 2 Claude calls (preflight ping + self-review); LinkedIn/Indeed are never invoked (Apify credits)
- During burn-in (until 2026-06-16) the same loop also rides along with every scan; this command exists for between-scan checkups and after any config surgery
- The sweep and health check are idempotent — safe to run repeatedly
