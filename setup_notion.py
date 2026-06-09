"""
One-time Notion setup script.
Creates two databases in your Notion workspace and writes their IDs to .env.

Before running:
  1. Go to https://www.notion.so and create a page (e.g. "Job Search Tracker")
  2. Open the page, click ··· → Connections → add your integration
  3. Copy the page URL and extract the page ID (last 32 chars before any ?)
  4. Run: python setup_notion.py --parent-page-id=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

After running, copy the printed DB IDs into your .env file.
"""
import argparse
import os
import sys

from dotenv import load_dotenv
load_dotenv()


_P1_DB_NAME = "P1 Backlog"
_P0_DB_NAME = "Ready to Apply"

_P1_PROPERTIES = {
    "Job Title": {"title": {}},
    "Company": {"rich_text": {}},
    "Score": {"number": {"format": "number"}},
    "Job URL": {"url": {}},
    "Source": {"select": {"options": [
        {"name": "Greenhouse", "color": "green"},
        {"name": "Lever", "color": "purple"},
        {"name": "Ashby", "color": "orange"},
        {"name": "Smartrecruiters", "color": "yellow"},
        {"name": "Linkedin", "color": "blue"},
        {"name": "Indeed", "color": "red"},
        {"name": "Wellfound", "color": "pink"},
        {"name": "Workday", "color": "gray"},
    ]}},
    "Location": {"rich_text": {}},
    "Date Found": {"date": {}},
    "Salary": {"rich_text": {}},
    "Score Breakdown": {"rich_text": {}},
    "Status": {"select": {"options": [
        {"name": "New", "color": "default"},
        {"name": "Reviewing", "color": "yellow"},
        {"name": "Applying", "color": "blue"},
        {"name": "Applied", "color": "green"},
        {"name": "Skipped", "color": "gray"},
    ]}},
    "Notes": {"rich_text": {}},
}

_P0_EXTRA = {
    "Resume GDoc": {"url": {}},
    "Tailoring Notes": {"rich_text": {}},
    "Interview Stage": {"select": {"options": [
        {"name": "Not Started", "color": "default"},
        {"name": "Phone Screen", "color": "yellow"},
        {"name": "Technical", "color": "orange"},
        {"name": "Onsite", "color": "red"},
        {"name": "Offer", "color": "green"},
        {"name": "Rejected", "color": "gray"},
    ]}},
}


def _create_db(client, parent_page_id: str, name: str, properties: dict) -> str:
    db = client.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": name}}],
        properties=properties,
    )
    return db["id"].replace("-", "")


def _normalize_page_id(raw: str) -> str:
    """Extract bare 32-char hex ID from URL or bare input."""
    import re
    # URL form: .../Page-Title-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    match = re.search(r"([0-9a-f]{32})", raw.replace("-", ""))
    if match:
        return match.group(1)
    return raw.replace("-", "")


def main():
    parser = argparse.ArgumentParser(description="Create Notion databases for job tracking")
    parser.add_argument("--parent-page-id", required=True, help="Notion page ID or URL")
    args = parser.parse_args()

    token = os.environ.get("NOTION_API_TOKEN", "")
    if not token:
        print("ERROR: NOTION_API_TOKEN not set in .env")
        sys.exit(1)

    try:
        from notion_client import Client
    except ImportError:
        print("ERROR: Run: pip install notion-client")
        sys.exit(1)

    client = Client(auth=token)
    page_id = _normalize_page_id(args.parent_page_id)

    print(f"Creating databases in page: {page_id}")

    # P1 Backlog
    print(f"  Creating '{_P1_DB_NAME}'...")
    p1_id = _create_db(client, page_id, _P1_DB_NAME, _P1_PROPERTIES)
    print(f"  ✓ P1 DB ID: {p1_id}")

    # P0 Ready to Apply (P1 props + extra)
    p0_props = {**_P1_PROPERTIES, **_P0_EXTRA}
    print(f"  Creating '{_P0_DB_NAME}'...")
    p0_id = _create_db(client, page_id, _P0_DB_NAME, p0_props)
    print(f"  ✓ P0 DB ID: {p0_id}")

    print("\n" + "=" * 60)
    print("Add these to your .env file:")
    print(f"  NOTION_P1_DB_ID={p1_id}")
    print(f"  NOTION_P0_DB_ID={p0_id}")
    print("=" * 60)

    # Auto-append to .env if it exists
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "a") as f:
            f.write(f"\nNOTION_P1_DB_ID={p1_id}\n")
            f.write(f"NOTION_P0_DB_ID={p0_id}\n")
        print("\n✓ Also appended to .env automatically")


if __name__ == "__main__":
    main()
