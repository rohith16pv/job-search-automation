Run Stage 2a: create tailored GDoc resumes for all P0 hot leads (score ≥ 70) that don't yet have one, then update column H in "P0 Hot Leads" with each GDoc URL.

## What this does
1. Reads `data/jobs_store.json` — the persistent store across all past scans
2. Filters to P0 jobs (score ≥ 70) with no GDoc URL yet (skips already-done ones)
3. For each pending P0 job:
   - Calls Groq (two-pass) to generate surgical text replacements tailored to that company + JD
   - Copies the base resume Google Doc (preserving fonts and layout)
   - Applies replacements, bolds key metrics, highlights changes yellow, flags reorder suggestion blue
   - Writes GDoc URL back to the store immediately (crash-safe)
4. Updates column H in "P0 Hot Leads" for each job with the new GDoc URL

## Steps
1. `cd /Users/rohith/Downloads/Github/job-search-automation`
2. Run: `python3 orchestrator.py --resume-only`
3. Stream and monitor the output
4. When complete, summarize:
   - How many P0 jobs were pending vs already done
   - How many GDocs were created this run
   - List each: Company — Role [Score] → GDoc URL
   - Confirm Sheets column H was updated
5. Remind the user:
   - 🟡 Yellow highlight = AI rewrote this paragraph
   - 🔵 Blue highlight = move this bullet to top for this JD

## Prerequisites
- Run `/job-auto-scan` first to populate the store
- Google OAuth token must be valid (run `python3 scripts/authorize_google.py` if expired)

## Notes
- The base resume is NEVER modified: https://docs.google.com/document/d/1EGRXaX2PC4JeFonhIUk1hEa1LizseUlDyNt7KurJDDc/edit
- Safe to run multiple times — already-processed jobs are skipped automatically
- Jobs accumulate across scans; nothing is lost if you scan again before running this
