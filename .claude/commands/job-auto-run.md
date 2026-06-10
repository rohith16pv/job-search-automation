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
- This is equivalent to running `/job-auto-scan` then `/job-auto-resume` back-to-back
- Stage 1 must complete successfully before Stage 2 starts
- Total runtime depends on job volume and Claude call latency (typically 5–15 min for a full run)
- Use `/job-auto-scan` and `/job-auto-resume-p0` separately if you want to review scored jobs before creating GDocs
- Run `/job-auto-resume-p1` separately after reviewing P1 rows in Sheets — not all P1 jobs warrant a tailored resume
