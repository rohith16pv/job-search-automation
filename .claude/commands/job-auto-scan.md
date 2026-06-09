Run Stage 1 of the job search pipeline: scout all job boards, score every posting against the base resume, and write P0 + P1 rows into Google Sheets.

## What this does
1. Fires all 11 scouts in parallel (Greenhouse, Lever, Ashby, LinkedIn, Indeed, Wellfound, SmartRecruiters, Workday, Google Careers, Amazon Jobs, Apple Jobs)
2. Deduplicates and applies hard filters (USA-only, posted ≤ 7 days)
3. Scores each job with keyword pre-filter + Groq AI deep scoring
4. Writes P0 (score ≥ 70) rows to "P0 Hot Leads" sheet — GDoc column left blank
5. Writes P1 (score 50–69) rows to "P1 Jobs" sheet
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

## Notes
- If a scout errors, others continue — errors are isolated
- The Groq rate limiter (25 RPM) auto-throttles — large batches may take a few minutes
- If GROQ_API_KEY is missing, scoring falls back to keyword-only mode
