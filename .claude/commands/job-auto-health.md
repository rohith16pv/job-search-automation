Run the pipeline health check: verify Claude auth, Google Sheets, Apify key, all configured ATS boards, and scout volume baselines — so a silently broken source never costs postings.

## Steps
1. `cd /Users/rohith/Downloads/Github/job-search-automation`
2. Run: `python3 scripts/health_check.py`
3. For the full Claude self-review (false-negative titles, scoring/query suggestions): `python3 scripts/health_check.py --review`
4. Summarize the results in chat.

## Error reporting
If ANY check fails or warns (dead ATS board, zero-count source, auth failure, stale last run), highlight it prominently in a dedicated "⚠ Issues" section — quote the exact line, explain what it means, and say what to do. If everything is healthy, say so in one line.

## Notes
- These same checks run automatically at the start of every daily scan; this command is for on-demand verification
- The weekly Claude self-review runs automatically on Sundays during the scan; suggestions land in `data/improvement_suggestions.md`
- Board auto-discovery runs after every scan: high-scoring LinkedIn/Indeed companies get their ATS boards probed and auto-added to `config/job_sources.yml`
