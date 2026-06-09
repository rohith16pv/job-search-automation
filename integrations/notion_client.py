"""
Notion integration — writes job records to the P1 Backlog and Ready to Apply databases.
Databases are created by setup_notion.py on first run.
"""
import os
from datetime import date
from typing import Optional
from agents.base import Job
from core.scorer import format_breakdown


class NotionClient:
    def __init__(self):
        try:
            from notion_client import Client
        except ImportError:
            raise RuntimeError("Run: pip install notion-client")

        token = os.environ.get("NOTION_API_TOKEN", "")
        if not token:
            raise RuntimeError("NOTION_API_TOKEN not set in .env")

        self._client = Client(auth=token)
        self._p1_db = os.environ.get("NOTION_P1_DB_ID", "")
        self._p0_db = os.environ.get("NOTION_P0_DB_ID", "")

        if not self._p1_db or not self._p0_db:
            raise RuntimeError(
                "NOTION_P1_DB_ID or NOTION_P0_DB_ID not set. "
                "Run: python setup_notion.py --parent-page-id=YOUR_PAGE_ID"
            )

    def _base_properties(self, job: Job) -> dict:
        salary = ""
        if job.salary_min and job.salary_max:
            salary = f"${job.salary_min:,} – ${job.salary_max:,}"
        elif job.salary_min:
            salary = f"${job.salary_min:,}+"

        return {
            "Job Title": {"title": [{"text": {"content": job.title[:200]}}]},
            "Company": {"rich_text": [{"text": {"content": job.company[:200]}}]},
            "Score": {"number": job.score},
            "Job URL": {"url": job.url or None},
            "Source": {"select": {"name": job.source.title()}},
            "Location": {"rich_text": [{"text": {"content": job.location[:200]}}]},
            "Date Found": {"date": {"start": str(date.today())}},
            "Salary": {"rich_text": [{"text": {"content": salary}}]},
            "Score Breakdown": {"rich_text": [{"text": {"content": format_breakdown(job)[:2000]}}]},
            "Status": {"select": {"name": "New"}},
        }

    def _already_exists(self, db_id: str, job: Job) -> bool:
        try:
            results = self._client.databases.query(
                database_id=db_id,
                filter={"property": "Job URL", "url": {"equals": job.url}},
            )
            return len(results.get("results", [])) > 0
        except Exception:
            return False

    def add_to_p1(self, job: Job) -> Optional[str]:
        if not self._p1_db:
            return None
        if self._already_exists(self._p1_db, job):
            return None
        props = self._base_properties(job)
        page = self._client.pages.create(
            parent={"database_id": self._p1_db},
            properties=props,
        )
        return page.get("url")

    def add_to_p0(self, job: Job) -> Optional[str]:
        if not self._p0_db:
            return None
        if self._already_exists(self._p0_db, job):
            return None
        props = self._base_properties(job)
        if job.resume_gdoc_url:
            props["Resume GDoc"] = {"url": job.resume_gdoc_url}
        if job.tailoring_notes:
            props["Tailoring Notes"] = {"rich_text": [{"text": {"content": job.tailoring_notes[:2000]}}]}
        page = self._client.pages.create(
            parent={"database_id": self._p0_db},
            properties=props,
        )
        return page.get("url")
