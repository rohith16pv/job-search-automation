Run the full end-to-end job search pipeline in one shot: scan all sources, score, write to Sheets, then create tailored GDocs for all P0 hot leads.

## What this does
Runs Stage 1 (scan + assess + Sheets write) immediately followed by Stage 2 (resume creation + Sheets GDoc update) without any pause.

## Steps
1. `cd /Users/rohith/Downloads/Github/job-search-automation`
2. Run Stage 1: `python3 orchestrator.py --scan-only`
3. Wait for it to complete
4. Run Stage 2: `python3 orchestrator.py --resume-only`
5. Wait for it to complete
6. When both finish, provide a full summary:
   - Jobs found per source
   - P0 / P1 / dropped counts
   - List every GDoc created: Company — Role → URL
   - Link to Google Sheets: https://docs.google.com/spreadsheets/d/$GOOGLE_SHEETS_ID

## Notes
- This is equivalent to running `/job-auto-scan` then `/job-auto-resume` back-to-back
- Stage 1 must complete successfully before Stage 2 starts
- Total runtime depends on job volume and Groq rate limits (typically 5–15 min for a full run)
- Use `/job-auto-scan` and `/job-auto-resume-p0` separately if you want to review scored jobs before creating GDocs
- Run `/job-auto-resume-p1` separately after reviewing P1 rows in Sheets — not all P1 jobs warrant a tailored resume
