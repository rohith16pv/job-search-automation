Run Stage 1 of the job search pipeline: scout all job boards, score every posting against the base resume, and write P0 + P1 rows into Google Sheets.

## What this does
1. Fires all 11 scouts in parallel (Greenhouse, Lever, Ashby, LinkedIn, Indeed, Wellfound, SmartRecruiters, Workday, Google Careers, Amazon Jobs, Apple Jobs)
2. Deduplicates and applies hard filters (USA-only, posted ≤ 20 days)
3. Scores each job with keyword pre-filter + Claude AI deep scoring
4. Writes P0 (score ≥ 70) rows to "P0 Hot Leads" sheet — GDoc column left blank
5. Writes P1 (score 50–69) rows to "P1 Jobs" sheet, P2 (40–49) to "P2 Review"
6. Saves `data/assessed_cache.json` for Stage 2

## Steps
1. `cd /Users/rohith/Downloads/Github/job-search-automation`
2. Run: `python3 orchestrator.py --scan-only`
3. Stream and monitor the output
4. When complete, summarize:
   - Total jobs found per source (from scout output)
   - How many passed dedup and hard filters
   - P0 count, P1 count, dropped count
   - Confirm Sheets rows were written
5. Tell the user: "Run `/job-auto-resume` to create tailored GDocs for all P0 hot leads."

## Burn-in week (until 2026-06-16) + self-improvement follow-up
After the run completes, ALWAYS do this follow-up:
1. Read the newest section of `data/improvement_suggestions.md` (the daily self-review writes it during burn-in, Sundays after).
2. Read any health warnings from the run output (dead boards, zero-count sources, volume drops).
3. FIX what is safely fixable right now, in this session: repoint or remove dead ATS slugs (probe for the company's new board first), repair broken scout endpoints, correct obvious config rot. Verify each fix live before finishing.
4. For judgment calls (scoring keyword changes, new queries, threshold moves): list them in chat as concrete proposals with a one-line rationale each, and apply the ones the user approves.
5. Report what was auto-fixed and what awaits approval in the summary.
The goal of the first week: every silent failure mode gets caught and fixed within 24h.

## Error reporting
If ANY error, warning, or issue appears in the output (aborted run, scout failures, dropped tailoring
swaps, GDoc/Sheets write errors, auth problems, anchor/keyword warnings), highlight it prominently in
the chat in a dedicated "⚠ Issues" section of your summary — quote the exact error line and say what
it means and what the user should do. Never bury an error mid-summary or omit it because the rest of
the run succeeded. If the run aborted, lead with that.

## Notes
- If a scout errors, others continue — errors are isolated
- Claude scoring runs sequentially via the claude CLI — large batches may take a few minutes
- If the claude CLI is missing or not logged in, the run ABORTS with a clear error (no keyword-only fallback) — run `claude` in a terminal and log in
