from __future__ import annotations

from uuid import uuid4

from fastapi import Request

REQUEST_ID_HEADER = "X-Request-Id"


def new_request_id() -> str:
    return f"req_{uuid4().hex}"


def get_request_id(request: Request) -> str:
    state_request_id = getattr(request.state, "request_id", None)
    if isinstance(state_request_id, str) and state_request_id:
        return state_request_id

    header_request_id = request.headers.get(REQUEST_ID_HEADER)
    if header_request_id:
        return header_request_id

    return new_request_id()
