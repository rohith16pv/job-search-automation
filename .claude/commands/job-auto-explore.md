Self-improve the scan capability: explore NEW reliable sources (companies, ATS platforms, job boards) and evolve the scanning filters (title matcher, scoring keywords, search queries) — with every change validated against live data before it ships. This is the expansion loop; `/job-auto-improve` is the repair loop.

## Mission
The user is a Senior PM targeting payments/fintech (Senior PM / PM II-III, USA/remote). A missed posting can be a lifeline. Each run of this skill should leave the system seeing MORE of the relevant job market than before, without letting junk in.

## Steps — execute in order

### 1. Inventory what we cover today
1. `cd /Users/rohith/Downloads/Github/job-search-automation`
2. Read `config/job_sources.yml` (companies per ATS, queries), `config/scoring.yml` (filters), and `data/exploration_log.json` if it exists (what previous runs already explored — do NOT redo it).
3. From `data/jobs_store.json`: which companies/sources produce the high scorers? Which produce nothing? (High-scorer companies' competitors are prime expansion targets.)

### 2. Explore new companies (every run)
1. Build a candidate list (~10–15 per run) of payments/fintech companies NOT in config: competitors and peers of stored high scorers, plus WebSearch for lists like "fintech companies hiring product managers", "payments startups series B+", recent fintech funding announcements. Prioritize US-presence companies in: money movement, issuing/acquiring, BaaS, treasury, fraud/risk, payroll, crypto/stablecoin payments, billing.
2. For each candidate: probe with `core.improve._probe_board(slug)` over `_slug_candidates(name)` variants (Greenhouse/Lever/Ashby).
3. Live board found → verify it has PM-relevant jobs, then add to `config/job_sources.yml` with `# explored YYYY-MM-DD`. No public board → record in the exploration log so future runs skip it (the LinkedIn/Indeed queries cover those companies).

### 3. Explore new source types (when prior runs haven't exhausted this)
Candidate ATSes/boards with public read APIs worth probing for our companies, in priority order:
- **Workable**: `GET https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true`
- **Recruitee**: `GET https://{slug}.recruitee.com/api/offers/`
- **SmartRecruiters** (already integrated — just add companies): `GET https://api.smartrecruiters.com/v1/companies/{slug}/postings`
- **Remotive / WeWorkRemotely / Built In** style boards: probe for stable JSON/RSS before considering
If ≥3 target companies live on an un-integrated ATS with a stable public API: write `agents/scout_{ats}.py` following the existing pattern exactly (async, shared `is_pm_title` from agents.base, Job fields incl. posted_date ISO, per-company error isolation, summary print), add a config section, wire it into `_run_scouts` in orchestrator.py, and live-test it. One new scout per run maximum — quality over breadth.

### 4. Evolve the filters (evidence only — never speculative)
1. **False negatives**: review `data/blocked_titles.jsonl` (and any sweep titles rejected by `is_pm_title`) — titles a payments Senior PM should have seen? Propose the precise pattern/keyword change.
2. **Keyword mining**: from the JDs of stored jobs scoring ≥70, extract recurring domain/skill terms missing from `config/scoring.yml` (e.g. emerging: stablecoin, RTP send, pay-by-bank, A2A). Propose tier placement.
3. **Query mining**: titles of stored high scorers that today's LinkedIn/Indeed queries would NOT have found → propose new query strings.
4. **Junk audit**: any stored sub-30 scores that keep arriving → propose a blocker only if it cannot hit a relevant title.

### 5. Validate EVERYTHING before shipping
- After ANY filter/scoring change: `python3 scripts/filter_regression.py --strict` — must pass (no known-good job gets buried). A regression means revert or fix, no exceptions.
- After ANY source/config change: `python3 scripts/scout_sweep.py` — total must be ≥ pre-change baseline; new sources must show jobs.
- New scout module: `python3 -m py_compile` + live run showing real PM jobs with titles/locations/descriptions mapped.

### 6. Change policy
- **Auto-apply**: new company boards on already-integrated ATSes; exploration-log updates.
- **Auto-apply with regression proof**: loosening changes (new perfect/domain/skills keywords, title-matcher widening) — these only ADD coverage; ship them if `filter_regression --strict` passes, and list them in the report.
- **Propose for approval**: new blockers or anything that REMOVES coverage (tightening), threshold moves, new scout modules go in the report with their live test output — user approves merging into the daily rotation.

### 7. Record + report
1. Update `data/exploration_log.json`: `{"explored_companies": {name: {date, result}}, "explored_sources": {name: {date, verdict}}, "runs": [...]}` — so each run starts where the last ended.
2. Report in chat: coverage added (companies/sources, with live job counts), filter changes shipped (with regression proof), proposals awaiting approval, dead ends recorded. Quote before/after sweep totals.

## Error reporting
Highlight any failure or warning prominently in a dedicated "⚠ Issues" section — exact line, meaning, action taken or decision needed.

## Notes
- Costs: no Claude scoring; WebSearch + HTTP probes + (optionally) a couple of Claude calls if you use it to brainstorm candidates. LinkedIn/Indeed actors are never invoked.
- Run cadence: weekly is plenty after burn-in; during burn-in (until 2026-06-16) running it 2–3× accelerates coverage growth.
- The scan's built-in discovery loop (core/improve.discover_boards) auto-adds companies that appear in search results; this skill goes further — it hunts companies that haven't appeared anywhere yet.
