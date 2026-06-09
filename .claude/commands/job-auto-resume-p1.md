Run Stage 2b: create tailored GDoc resumes for all P1 backlog jobs (score 50–69) that don't yet have one, then update column H in "P1 Jobs" with each GDoc URL.

## What this does
1. Reads `data/jobs_store.json` — the persistent store across all past scans
2. Filters to P1 jobs (score 50–69) with no GDoc URL yet (skips already-done ones)
3. For each pending P1 job:
   - Calls Groq (two-pass) to generate surgical text replacements tailored to that company + JD
   - Copies the base resume Google Doc (preserving fonts and layout)
   - Applies replacements, bolds key metrics, highlights changes yellow, flags reorder suggestion blue
   - Writes GDoc URL back to the store immediately (crash-safe)
4. Updates column H in "P1 Jobs" for each job with the new GDoc URL

## Steps
1. `cd /Users/rohith/Downloads/Github/job-search-automation`
2. Run: `python3 orchestrator.py --resume-p1`
3. Stream and monitor the output
4. When complete, summarize:
   - How many P1 jobs were pending vs already done
   - How many GDocs were created this run
   - List each: Company — Role [Score] → GDoc URL
   - Confirm Sheets column H was updated

## Prerequisites
- Run `/job-auto-scan` first to populate the store
- Google OAuth token must be valid (run `python3 scripts/authorize_google.py` if expired)

## Notes
- P1 jobs are moderate fits (50–69). Resumes are still fully tailored — same quality as P0.
- Use this selectively: not every P1 job warrants a tailored resume. Run after reviewing P1 rows in Sheets.
- Safe to run multiple times — already-processed jobs are skipped automatically
- The base resume is NEVER modified: https://docs.google.com/document/d/1EGRXaX2PC4JeFonhIUk1hEa1LizseUlDyNt7KurJDDc/edit
