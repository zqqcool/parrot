from __future__ import annotations

import logging
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ExceptionHandler

from app.core.error_messages import public_error_message
from app.core.request_id import get_request_id
from app.core.response import ApiErrorResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, cast(ExceptionHandler, handle_app_error))
    app.add_exception_handler(StarletteHTTPException, cast(ExceptionHandler, handle_http_error))
    app.add_exception_handler(
        RequestValidationError, cast(ExceptionHandler, handle_validation_error)
    )
    app.add_exception_handler(Exception, handle_unexpected_error)


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(
        request,
        exc.status_code,
        exc.code,
        public_error_message(exc.code),
        exc.details,
    )


async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code, message = _http_error(exc.status_code)
    return _error_response(request, exc.status_code, code, message)


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "reason": error["msg"],
        }
        for error in exc.errors()
    ]
    return _error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "VALIDATION_ERROR",
        public_error_message("VALIDATION_ERROR"),
        details,
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled request failure",
        extra={"request_id": get_request_id(request), "path": request.url.path},
        exc_info=exc,
    )
    return _error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "INTERNAL_ERROR",
        public_error_message("INTERNAL_ERROR"),
    )


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, str]] | None = None,
) -> JSONResponse:
    body = ApiErrorResponse(
        code=code,
        message=message,
        details=details or [],
        request_id=get_request_id(request),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


def _http_error(status_code: int) -> tuple[str, str]:
    values = {
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "RESOURCE_NOT_FOUND",
        status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    }
    code = values.get(status_code, "HTTP_ERROR")
    return code, public_error_message(code)
