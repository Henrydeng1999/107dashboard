from datetime import datetime

from pydantic import BaseModel


class GitRepositorySummary(BaseModel):
    id: str
    name: str
    relative_path: str
    branch: str
    head: str | None
    dirty: bool
    changed_files: int
    last_commit_at: datetime | None


class GitRepositoryList(BaseModel):
    enabled: bool
    items: list[GitRepositorySummary]


class GitChangedFile(BaseModel):
    status: str
    path: str


class GitCommitSummary(BaseModel):
    hash: str
    short_hash: str
    subject: str
    author_name: str
    authored_at: datetime


class GitRepositoryDetail(BaseModel):
    repository: GitRepositorySummary
    changes: list[GitChangedFile]
    commits: list[GitCommitSummary]
    readme_name: str | None
    readme_content: str | None
    readme_truncated: bool


class GitCommitDetail(GitCommitSummary):
    body: str
    files: list[GitChangedFile]

