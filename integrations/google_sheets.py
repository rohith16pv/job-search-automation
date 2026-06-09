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

Columns (A–J):
  Date | Company | Job Title | Score | Location | Source | Job URL | Resume GDoc | Salary | Status
"""
import asyncio
import os
from datetime import date
from agents.base import Job

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


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
        """Write column headers to row 1 if the tab is empty."""
        self._ensure_tab_exists(service, sheet_name)
        result = service.spreadsheets().values().get(
            spreadsheetId=self._sheet_id,
            range=f"{sheet_name}!A1:J1",
        ).execute()
        if not result.get("values"):
            headers = [[
                "Date", "Company", "Job Title", "Score", "Location",
                "Source", "Job URL", "Resume GDoc", "Salary", "Status",
            ]]
            service.spreadsheets().values().update(
                spreadsheetId=self._sheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": headers},
            ).execute()

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

    def _find_row_by_url(self, service, sheet_name: str, job_url: str) -> int | None:
        """Return 1-based row index where column G matches job_url, or None."""
        result = service.spreadsheets().values().get(
            spreadsheetId=self._sheet_id,
            range=f"{sheet_name}!A:J",
        ).execute()
        for i, row in enumerate(result.get("values", []), start=1):
            if len(row) > 6 and row[6] == job_url:
                return i
        return None

    def _update_cell(self, service, sheet_name: str, row: int, col: str, value: str) -> None:
        service.spreadsheets().values().update(
            spreadsheetId=self._sheet_id,
            range=f"{sheet_name}!{col}{row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[value]]},
        ).execute()

    async def update_gdoc_url(self, job: Job) -> None:
        """Find the job's row in P0 Hot Leads (by URL) and write GDoc URL to column H."""
        if not self._enabled:
            return
        try:
            def _do():
                svc = self._get_service()
                row = self._find_row_by_url(svc, "P0 Hot Leads", job.url)
                if row:
                    self._update_cell(svc, "P0 Hot Leads", row, "H", job.resume_gdoc_url or "")
                    print(f"  [sheets] updated GDoc URL for {job.company} (row {row})")
                else:
                    print(f"  [sheets] row not found for {job.company} — appending instead")
                    self._append_row("P0 Hot Leads", [
                        "", job.company, job.title, job.score, job.location,
                        job.source, job.url, job.resume_gdoc_url or "", "", "Resume Ready",
                    ])
            await asyncio.to_thread(_do)
        except Exception as e:
            print(f"  [sheets] update_gdoc_url failed ({job.company}): {e}")

    async def add_row(self, sheet_name: str, job: Job) -> None:
        if not self._enabled:
            return
        salary = ""
        if job.salary_min and job.salary_max:
            salary = f"${job.salary_min:,}–${job.salary_max:,}"
        row = [
            str(date.today()),
            job.company,
            job.title,
            job.score,
            job.location,
            job.source,
            job.url,
            job.resume_gdoc_url or "",
            salary,
            "New",
        ]
        try:
            await asyncio.to_thread(self._append_row, sheet_name, row)
        except Exception as e:
            print(f"  [sheets] append failed ({sheet_name}): {e}")
