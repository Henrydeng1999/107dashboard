from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.schemas.jobs import TestProjectListResponse, TestProjectResponse
from app.services.test_projects import TestProjectCatalog, TestProjectError

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=TestProjectListResponse)
def test_projects(request: Request) -> TestProjectListResponse | JSONResponse:
    catalog: TestProjectCatalog | None = request.app.state.test_project_catalog
    if catalog is None:
        return TestProjectListResponse(items=[])
    try:
        projects = catalog.list_projects()
    except TestProjectError:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "TEST_PROJECTS_UNAVAILABLE",
                    "message": "Test projects are temporarily unavailable",
                    "request_id": request.state.request_id,
                }
            },
        )
    return TestProjectListResponse(
        items=[
            TestProjectResponse(
                id=project.id,
                name=project.name,
                description=project.description,
                entrypoint=project.entrypoint,
                expected_outcome=project.expected_outcome,
                command=project.command,
                resources=project.resources,
            )
            for project in projects
        ]
    )
