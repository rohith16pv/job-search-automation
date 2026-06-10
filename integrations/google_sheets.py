"""
Google Sheets integration — appends job rows to the tracking spreadsheet.

Setup:
  - Set GOOGLE_SERVICE_ACCOUNT_JSON=config/google_service_account.json in .env
  - Set GOOGLE_SHEETS_ID=<your spreadsheet id> in .env
  - Share the spreadsheet with the service account email (Editor access):
      job-hunt@project-job-automation-498906.iam.gserviceaccount.com

Sheet tabs:
  - "P0 Hot Leads"  — score ≥ 70  (with tailored resume GDoc link)
  - "P1 Jobs"       — score 50–69

Columns (A–L):
  Posted Date | Date Added | Company | Role | Status | ATS Pre-Score |
  ATS Post-Mod Score | Location | Portal Source | Job Link | Resume GDoc | Notes

Tabs still on the old 10-column layout (Date | Company | Job Title | ...) are
migrated in place automatically the first time a row is written.
"""
import asyncio
import os
from datetime import date
from typing import Optional
from agents.base import Job

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = [
    "Posted Date", "Date Added", "Company", "Role", "Status", "ATS Pre-Score",
    "ATS Post-Mod Score", "Location", "Portal Source", "Job Link", "Resume GDoc", "Notes",
]

_OLD_HEADERS = [
    "Date", "Company", "Job Title", "Score", "Location",
    "Source", "Job URL", "Resume GDoc", "Salary", "Status",
]

# Column letters for cells updated after row creation
_COL_POST_SCORE = "G"
_COL_JOB_LINK_IDX = 9   # 0-based index of "Job Link" (column J)
_COL_GDOC = "K"


def _load_creds():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        return None
    if not os.path.isabs(raw):
        raw = os.path.join(os.path.dirname(__file__), "..", raw)
    path = os.path.normpath(raw)
    if not os.path.exists(path):
        return None
    from google.oauth2 import service_account
    return service_account.Credentials.from_service_account_file(path, scopes=_SCOPES)


def _cell(value: str) -> str:
    """Neutralize spreadsheet formula injection in scraped text: a job title or
    company starting with '=', '+' or '@' would otherwise be evaluated as a
    formula under USER_ENTERED (e.g. =IMPORTXML exfiltration)."""
    s = str(value)
    return "'" + s if s[:1] in ("=", "+", "@") else s


def _job_row(job: Job, status: str = "New") -> list:
    """Build a row in the A–L schema from a Job."""
    salary = ""
    if job.salary_min and job.salary_max:
        salary = f"Salary: ${job.salary_min:,}–${job.salary_max:,}"
    return [
        _cell(job.posted_date or ""),
        str(date.today()),
        _cell(job.company),
        _cell(job.title),
        status,
        job.score,
        getattr(job, "ats_post_score", "") or "",
        _cell(job.location),
        _cell(job.source),
        _cell(job.url),
        job.resume_gdoc_url or "",
        _cell(salary),
    ]


def _serial_to_iso(value: str) -> str:
    """Convert a Sheets serial-number date (e.g. '46182') to ISO, pass others through."""
    v = value.strip()
    if v.isdigit() and 40000 < int(v) < 60000:  # plausible serial range ≈ 2009–2064
        from datetime import timedelta
        return str(date(1899, 12, 30) + timedelta(days=int(v)))
    return value


def _migrate_old_row(old: list) -> list:
    """Map an old 10-column row (Date|Company|Job Title|Score|Location|Source|
    Job URL|Resume GDoc|Salary|Status) to the new A–L schema."""
    old = old + [""] * (10 - len(old))
    salary = old[8].strip()
    return [
        "",                                   # Posted Date (unknown for old rows)
        _serial_to_iso(old[0]),               # Date Added ← old Date
        old[1],                               # Company
        old[2],                               # Role ← Job Title
        old[9] or "New",                      # Status
        old[3],                               # ATS Pre-Score ← Score
        "",                                   # ATS Post-Mod Score
        old[4],                               # Location
        old[5],                               # Portal Source ← Source
        old[6],                               # Job Link ← Job URL
        old[7],                               # Resume GDoc
        f"Salary: {salary}" if salary else "",  # Notes ← Salary
    ]


class SheetsClient:
    def __init__(self):
        self._sheet_id = os.environ.get("GOOGLE_SHEETS_ID", "")
        creds = _load_creds()
        self._enabled = bool(creds and self._sheet_id)
        self._creds = creds

        if not self._enabled:
            if not self._sheet_id:
                print("  [sheets] skipped — GOOGLE_SHEETS_ID not set")
            elif creds is None:
                print("  [sheets] skipped — GOOGLE_SERVICE_ACCOUNT_JSON missing or not found")

    def _get_service(self):
        from googleapiclient.discovery import build
        return build("sheets", "v4", credentials=self._creds)

    def _ensure_tab_exists(self, service, sheet_name: str) -> None:
        """Create the tab if it doesn't exist yet."""
        meta = service.spreadsheets().get(spreadsheetId=self._sheet_id).execute()
        existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if sheet_name not in existing:
            service.spreadsheets().batchUpdate(
                spreadsheetId=self._sheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
            ).execute()
            print(f"  [sheets] created tab '{sheet_name}'")

    def _ensure_headers(self, service, sheet_name: str) -> None:
        """Write headers if the tab is empty; migrate in place if it still
        uses the old 10-column layout; warn loudly on an unknown layout."""
        self._ensure_tab_exists(service, sheet_name)
        result = service.spreadsheets().values().get(
            spreadsheetId=self._sheet_id,
            range=f"{sheet_name}!A:L",
        ).execute()
        rows = result.get("values", [])

        if not rows:
            service.spreadsheets().values().update(
                spreadsheetId=self._sheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": [HEADERS]},
            ).execute()
            return

        header = [c.strip() for c in rows[0]]
        if header == HEADERS:
            return

        if header == _OLD_HEADERS:
            print(f"  [sheets] migrating '{sheet_name}' to the new 12-column layout ({len(rows) - 1} rows)")
            migrated = [HEADERS] + [_migrate_old_row(r) for r in rows[1:]]
            service.spreadsheets().values().update(
                spreadsheetId=self._sheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": migrated},
            ).execute()
            print(f"  [sheets] '{sheet_name}' migrated")
            return

        print(
            f"  [sheets] ⚠ '{sheet_name}' has an unrecognized header row — appending in the "
            f"new A–L order anyway. Review the tab: columns may be misaligned."
        )

    def _append_row(self, sheet_name: str, row: list) -> None:
        service = self._get_service()
        self._ensure_headers(service, sheet_name)
        service.spreadsheets().values().append(
            spreadsheetId=self._sheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

    def _find_row_by_url(self, service, sheet_name: str, job_url: str) -> Optional[int]:
        """Return 1-based row index where the Job Link column matches job_url, or None."""
        result = service.spreadsheets().values().get(
            spreadsheetId=self._sheet_id,
            range=f"{sheet_name}!A:L",
        ).execute()
        for i, row in enumerate(result.get("values", []), start=1):
            if len(row) > _COL_JOB_LINK_IDX and row[_COL_JOB_LINK_IDX] == job_url:
                return i
        return None

    def _update_cell(self, service, sheet_name: str, row: int, col: str, value: str) -> None:
        service.spreadsheets().values().update(
            spreadsheetId=self._sheet_id,
            range=f"{sheet_name}!{col}{row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[value]]},
        ).execute()

    async def update_gdoc_url(self, job: Job, sheet_name: str = "P0 Hot Leads") -> bool:
        """Find the job's row (by Job Link) and write the Resume GDoc URL (col K)
        plus the ATS Post-Mod Score (col G) if the tailor computed one.
        Returns False on failure so the caller can flag the job for retry
        (when disabled, returns True — there is nothing to sync)."""
        if not self._enabled:
            return True
        try:
            def _do():
                svc = self._get_service()
                self._ensure_headers(svc, sheet_name)  # migrates old layout before column writes
                row = self._find_row_by_url(svc, sheet_name, job.url)
                if row:
                    self._update_cell(svc, sheet_name, row, _COL_GDOC, job.resume_gdoc_url or "")
                    post = getattr(job, "ats_post_score", "") or ""
                    if post:
                        self._update_cell(svc, sheet_name, row, _COL_POST_SCORE, post)
                    self._update_cell(svc, sheet_name, row, "E", "Resume Ready")
                    print(f"  [sheets] updated GDoc URL for {job.company} (row {row})")
                else:
                    print(f"  [sheets] row not found for {job.company} — appending instead")
                    self._append_row(sheet_name, _job_row(job, status="Resume Ready"))
            await asyncio.to_thread(_do)
            return True
        except Exception as e:
            print(f"  [sheets] ⚠ update_gdoc_url failed ({job.company}): {e}")
            return False

    async def add_row(self, sheet_name: str, job: Job) -> bool:
        """Append the job's row. Returns False on failure so the caller can
        flag the job for retry (when disabled, returns True)."""
        if not self._enabled:
            return True
        try:
            await asyncio.to_thread(self._append_row, sheet_name, _job_row(job))
            return True
        except Exception as e:
            print(f"  [sheets] ⚠ append failed ({sheet_name}, {job.company}): {e}")
            return False

    async def upsert_row(self, sheet_name: str, job: Job) -> bool:
        """Append the job's row only if no row with its Job Link exists yet.
        Used by retry passes so a row whose first publish attempt actually
        landed is never duplicated."""
        if not self._enabled:
            return True
        try:
            def _do():
                svc = self._get_service()
                self._ensure_headers(svc, sheet_name)
                if self._find_row_by_url(svc, sheet_name, job.url) is None:
                    self._append_row(sheet_name, _job_row(job))
                    print(f"  [sheets] published missing row for {job.company} ({sheet_name})")
            await asyncio.to_thread(_do)
            return True
        except Exception as e:
            print(f"  [sheets] ⚠ upsert failed ({sheet_name}, {job.company}): {e}")
            return False
