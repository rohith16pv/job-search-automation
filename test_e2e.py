"""
End-to-end test with 2 hardcoded job URLs.

Bypasses all scouts — manually defines 2 jobs, then runs the full
score → tailor → GDoc → Sheets pipeline.

Usage:
    python3 test_e2e.py
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from agents.base import Job, make_job_id
from core.scorer import score_jobs_batch
from core.resume_tailor import tailor_resume
from integrations.google_docs import read_resume_from_gdoc
from integrations.google_sheets import SheetsClient

# ── Paste any 2 job URLs + details here ──────────────────────────────────────
TEST_JOBS = [
    Job(
        id=make_job_id("https://www.linkedin.com/jobs/view/test-job-1"),
        title="Senior Product Manager, Payments",
        company="Stripe",
        url="https://stripe.com/jobs/listing/senior-product-manager-payments",
        location="Remote, USA",
        source="test",
        posted_date="2026-06-09",
        description="""
        We are looking for a Senior Product Manager to lead our payments infrastructure
        products. You will own the roadmap for ACH, RTP, and card payment rails.

        Responsibilities:
        - Define and execute the product strategy for payment settlement products
        - Work cross-functionally with engineering, compliance, and operations
        - Drive adoption of real-time payment rails with enterprise customers
        - Define success metrics, run A/B tests, and iterate based on data

        Requirements:
        - 5+ years of product management experience in payments or fintech
        - Deep knowledge of payment rails: ACH, RTP, wire, card networks
        - Experience with API-first products and developer platforms
        - Strong data and analytics skills (SQL, experimentation)
        - Track record of shipping 0-to-1 and scaled products
        """,
    ),
    Job(
        id=make_job_id("https://www.linkedin.com/jobs/view/test-job-2"),
        title="Staff Product Manager, Embedded Finance",
        company="Plaid",
        url="https://plaid.com/careers/openings/staff-product-manager-embedded-finance",
        location="San Francisco, CA / Remote",
        source="test",
        posted_date="2026-06-09",
        description="""
        Plaid is hiring a Staff PM to lead embedded finance products that help
        developers build financial services into their apps.

        What you'll do:
        - Own the product vision for Plaid's embedded finance API suite
        - Partner with banking partners, fintech customers, and regulators
        - Drive compliance and risk frameworks (KYC, AML, PSD2)
        - Scale infrastructure to handle $2B+ daily transaction volume
        - Lead a cross-functional team across 3 time zones

        What we're looking for:
        - 7+ years PM experience, 3+ in fintech or embedded finance
        - Experience with open banking, PSD2, or bank API integrations
        - Strong grasp of fraud, KYC/AML, and regulatory requirements
        - Proven ability to influence without authority across engineering and legal
        """,
    ),
]
# ─────────────────────────────────────────────────────────────────────────────


async def run():
    print("=" * 60)
    print("  E2E Test — 2 jobs")
    print("=" * 60)

    # Step 1: Load resume
    print("\n[1/4] Loading resume from Google Doc...")
    resume_text = await read_resume_from_gdoc()
    if not resume_text:
        print("  WARNING: resume empty — scoring will use keyword fallback only")

    # Step 2: Score
    print("\n[2/4] Scoring jobs against resume...")
    scored = await score_jobs_batch(TEST_JOBS, resume_text)
    scored.sort(key=lambda j: j.score, reverse=True)
    for job in scored:
        print(f"  [{job.score:3d}] {job.title} @ {job.company}")

    # Step 3: Tailor + create GDocs
    print("\n[3/4] Creating tailored resume GDocs...")
    for job in scored:
        print(f"\n  → {job.title} @ {job.company}")
        gdoc_url = await tailor_resume(job, resume_text)
        job.resume_gdoc_url = gdoc_url
        if gdoc_url.startswith("http"):
            print(f"    GDoc: {gdoc_url}")
        else:
            print(f"    Saved locally: {gdoc_url}")

    # Step 4: Write to Google Sheets
    print("\n[4/4] Writing to Google Sheets...")
    sheets = SheetsClient()
    for job in scored:
        sheet_name = "P0 Hot Leads" if job.score >= 70 else "P1 Jobs"
        await sheets.add_row(sheet_name, job)
        print(f"  Written to '{sheet_name}': {job.company}")

    print("\n" + "=" * 60)
    print("  TEST COMPLETE")
    print("=" * 60)
    sheets_id = os.environ.get("GOOGLE_SHEETS_ID", "")
    if sheets_id:
        print(f"\nCheck your sheet:")
        print(f"  https://docs.google.com/spreadsheets/d/{sheets_id}")


if __name__ == "__main__":
    asyncio.run(run())
