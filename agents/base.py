from dataclasses import dataclass, field
import hashlib


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

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Job) and self.id == other.id


def make_job_id(url: str) -> str:
    return hashlib.md5(url.strip().encode()).hexdigest()
