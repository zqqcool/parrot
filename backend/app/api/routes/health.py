from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette import status

from app.core.errors import AppError
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok

router = APIRouter()


class HealthData(BaseModel):
    status: str
    app_name: str
    environment: str
    dependencies: dict[str, str] = Field(default_factory=dict)


@router.get("/health/live", response_model=ApiResponse[HealthData])
async def liveness(request: Request) -> ApiResponse[HealthData]:
    settings = request.app.state.settings
    return ok(
        HealthData(
            status="ok",
            app_name=settings.app.name,
            environment=settings.app.environment,
        ),
        get_request_id(request),
    )


@router.get("/health/ready", response_model=ApiResponse[HealthData])
async def readiness(request: Request) -> ApiResponse[HealthData]:
    database_ok = await request.app.state.database.ping()
    redis_ok = await request.app.state.redis.ping()
    if not database_ok or not redis_ok:
        raise AppError(
            "DEPENDENCY_UNAVAILABLE",
            "Application dependencies are not ready",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    settings = request.app.state.settings
    return ok(
        HealthData(
            status="ready",
            app_name=settings.app.name,
            environment=settings.app.environment,
            dependencies={"database": "ok", "redis": "ok"},
        ),
        get_request_id(request),
    )
