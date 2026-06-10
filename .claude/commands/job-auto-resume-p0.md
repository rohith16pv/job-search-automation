Run Stage 2a: create tailored GDoc resumes for all P0 hot leads (score ≥ 70) that don't yet have one, then update the Resume GDoc column (K), ATS Post-Mod Score (G), and Status in "P0 Hot Leads".

## What this does
1. Reads `data/jobs_store.json` — the persistent store across all past scans
2. Filters to P0 jobs (score ≥ 70) with no GDoc URL yet (skips already-done ones)
3. For each pending P0 job:
   - Calls Claude (two-pass) to generate surgical text replacements tailored to that company + JD
   - Copies the base resume Google Doc (preserving fonts and layout)
   - Applies replacements, bolds key metrics, highlights changes yellow, flags reorder suggestion blue
   - Writes GDoc URL back to the store immediately (crash-safe)
4. Updates Resume GDoc (col K), ATS Post-Mod Score (col G), and Status in "P0 Hot Leads" for each job

## Steps
1. `cd /Users/rohith/Downloads/Github/job-search-automation`
2. Run: `python3 orchestrator.py --resume-only`
3. Stream and monitor the output
4. When complete, summarize:
   - How many P0 jobs were pending vs already done
   - How many GDocs were created this run
   - List each: Company — Role [Score] → GDoc URL
   - Confirm the Resume GDoc and ATS Post-Mod Score columns were updated
5. Remind the user:
   - 🟡 Yellow highlight = AI rewrote this paragraph
   - 🔵 Blue highlight = move this bullet to top for this JD

## Prerequisites
- Run `/job-auto-scan` first to populate the store
- Google OAuth token must be valid (run `python3 scripts/authorize_google.py` if expired)

## Error reporting
If ANY error, warning, or issue appears in the output (aborted run, scout failures, dropped tailoring
swaps, GDoc/Sheets write errors, auth problems, anchor/keyword warnings), highlight it prominently in
the chat in a dedicated "⚠ Issues" section of your summary — quote the exact error line and say what
it means and what the user should do. Never bury an error mid-summary or omit it because the rest of
the run succeeded. If the run aborted, lead with that.

## Notes
- The base resume is NEVER modified: https://docs.google.com/document/d/1EGRXaX2PC4JeFonhIUk1hEa1LizseUlDyNt7KurJDDc/edit
- Safe to run multiple times — already-processed jobs are skipped automatically
- Jobs accumulate across scans; nothing is lost if you scan again before running this
