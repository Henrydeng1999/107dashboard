from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse

from app.schemas.repositories import GitCommitDetail, GitRepositoryDetail, GitRepositoryList
from app.services.repositories import (
    GitRepositoryBrowser,
    GitRepositoryNotFound,
    GitRepositoryUnavailable,
)

router = APIRouter(prefix="/repositories", tags=["repositories"])


def browser(request: Request) -> GitRepositoryBrowser:
    return request.app.state.git_repository_browser


Browser = Annotated[GitRepositoryBrowser, Depends(browser)]
RepositoryId = Annotated[str, Path(pattern=r"^[a-f0-9]{16}$")]
Revision = Annotated[str, Path(pattern=r"^[a-f0-9]{40}$")]


def error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request.state.request_id}},
    )


@router.get("", response_model=GitRepositoryList)
def repositories(request: Request, service: Browser):
    try:
        return GitRepositoryList(enabled=service.enabled, items=service.repositories())
    except GitRepositoryUnavailable:
        return error(request, 503, "GIT_UNAVAILABLE", "Git repository data is unavailable")


@router.get("/{repository_id}", response_model=GitRepositoryDetail)
def repository(repository_id: RepositoryId, request: Request, service: Browser):
    try:
        return service.detail(repository_id)
    except GitRepositoryNotFound:
        return error(request, 404, "REPOSITORY_NOT_FOUND", "Repository was not found")
    except GitRepositoryUnavailable:
        return error(request, 503, "GIT_UNAVAILABLE", "Git repository data is unavailable")


@router.get("/{repository_id}/commits/{revision}", response_model=GitCommitDetail)
def commit(repository_id: RepositoryId, revision: Revision, request: Request, service: Browser):
    try:
        return service.commit(repository_id, revision)
    except GitRepositoryNotFound:
        return error(request, 404, "COMMIT_NOT_FOUND", "Commit was not found")
    except GitRepositoryUnavailable:
        return error(request, 503, "GIT_UNAVAILABLE", "Git repository data is unavailable")
