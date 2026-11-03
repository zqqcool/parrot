from __future__ import annotations

from pydantic import BaseModel, Field


class ApiResponse[T](BaseModel):
    code: str = "OK"
    message: str = "success"
    data: T
    request_id: str


class ApiErrorResponse(BaseModel):
    code: str
    message: str
    details: list[dict[str, str]] = Field(default_factory=list[dict[str, str]])
    request_id: str


def ok[T](data: T, request_id: str, message: str = "success") -> ApiResponse[T]:
    return ApiResponse(message=message, data=data, request_id=request_id)
