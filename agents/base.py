from dataclasses import dataclass, field
import hashlib
import re

# Shared scout-level title filter — intentionally LOOSE. Its only job is to keep
# obviously-non-PM roles (engineers, designers, sales) out of the pipeline; the
# scorer and Claude decide what's actually relevant. Catches short forms
# ("Senior PM, Payments"), "Product Management" titles (Capital One style),
# and Product Owner variants that exact-phrase lists missed.
_PM_TITLE_RE = re.compile(
    r"product manager|product management|product lead|product owner"
    r"|head of product|director of product|director, product|vp.{0,4}product"
    r"|principal product|staff product|group product"
    r"|\bpm\b",
    re.IGNORECASE,
)


def is_pm_title(title: str) -> bool:
    return bool(_PM_TITLE_RE.search(title or ""))


@dataclass
class Job:
    id: str
    title: str
    company: str
    url: str
    description: str
    location: str
    source: str
    posted_date: str = ""
    salary_min: int = 0
    salary_max: int = 0
    score: int = 0
    score_breakdown: dict = field(default_factory=dict)
    resume_gdoc_url: str = ""
    tailoring_notes: str = ""
    ats_post_score: str = ""  # JD keyword coverage after tailoring, e.g. "77%"

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Job) and self.id == other.id


def make_job_id(url: str) -> str:
    return hashlib.md5(url.strip().encode()).hexdigest()
