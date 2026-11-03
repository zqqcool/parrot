"""Local-only, stateless MCP and HTTP echo service for integration tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections.abc import Sequence
from typing import Final

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

LOGGER = logging.getLogger("mcp_api_echo_demo")
SENSITIVE_HEADERS: Final = frozenset(
    {"authorization", "cookie", "proxy-authorization", "set-cookie", "x-api-key"}
)
TICKET_REQUIRED_FIELDS: Final = (
    "contact_name",
    "contact_method",
    "city",
    "business_need",
)


def decode_payload(raw_body: bytes) -> object:
    """Keep JSON structured when possible and make arbitrary HTTP bodies printable."""
    if not raw_body:
        return None
    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body.decode("utf-8", errors="replace")


def safe_headers(request: Request) -> dict[str, str]:
    """Exclude transport credentials while retaining useful protocol diagnostics."""
    return {
        name: "<redacted>" if name.lower() in SENSITIVE_HEADERS else value
        for name, value in request.headers.items()
    }


def log_request(protocol: str, payload: object, **details: object) -> None:
    """Print one structured event without retaining any client state."""
    event = {"protocol": protocol, **details, "payload": payload}
    LOGGER.info("client request: %s", json.dumps(event, ensure_ascii=False, default=str))


def create_test_ticket(
    contact_name: str,
    contact_method: str,
    city: str,
    business_need: str,
    requested_time: str | None = None,
    confirmed: bool = False,
) -> dict[str, object]:
    """Create a deterministic ticket-shaped test result without persisting user data."""
    values = {
        "contact_name": contact_name.strip(),
        "contact_method": contact_method.strip(),
        "city": city.strip(),
        "business_need": business_need.strip(),
        "requested_time": requested_time.strip() if requested_time else "",
    }
    missing_fields = [field for field in TICKET_REQUIRED_FIELDS if not values[field]]
    if missing_fields:
        return {
            "status": "rejected",
            "code": "TICKET_INPUT_INCOMPLETE",
            "missing_fields": missing_fields,
        }
    if not confirmed:
        return {
            "status": "rejected",
            "code": "TICKET_CONFIRMATION_REQUIRED",
            "message": "The user must explicitly confirm test ticket creation.",
        }
    ticket_id = _ticket_id(values)
    log_request(
        "mcp",
        {
            "ticket_id": ticket_id,
            "fields": TICKET_REQUIRED_FIELDS,
            "requested_time_provided": bool(values["requested_time"]),
        },
        tool="create_ticket",
    )
    return {
        "status": "created",
        "ticket_id": ticket_id,
        "test_only": True,
        "message": "A test ticket was created without writing to an external system.",
    }


def _ticket_id(values: dict[str, str]) -> str:
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"TEST-TICKET-{hashlib.sha256(encoded).hexdigest()[:12].upper()}"


def create_mcp_server() -> FastMCP:
    """Build the MCP server with standard stateless Streamable HTTP transport."""
    server = FastMCP(
        "Request Echo MCP",
        instructions=(
            "Call echo with any payload, or create_ticket after the user has explicitly confirmed. "
            "Ticket results are local test data and never write to an external system."
        ),
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
    )

    async def echo(payload: object) -> dict[str, object]:
        log_request("mcp", payload, tool="echo")
        return {"protocol": "mcp", "received": payload}

    server.tool(name="echo", description="Log and return the supplied test payload.")(echo)
    server.tool(
        name="create_ticket",
        description=(
            "Create a test-only service ticket after explicit user confirmation. "
            "It returns a ticket ID without persisting or echoing personal details."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True),
    )(create_test_ticket)
    return server


async def print_incoming_request(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Print all incoming requests while preserving the body for their handler."""
    raw_body = await request.body()
    log_request(
        "http",
        decode_payload(raw_body),
        method=request.method,
        path=request.url.path,
        query=request.url.query,
        headers=safe_headers(request),
    )
    return await call_next(request)


async def api_echo(request: Request) -> JSONResponse:
    """Return exactly the request body received by the normal HTTP API."""
    return JSONResponse({"protocol": "http", "received": decode_payload(await request.body())})


def create_app() -> Starlette:
    """Build an app with one HTTP echo endpoint and one MCP endpoint at /mcp."""
    app = create_mcp_server().streamable_http_app()
    app.add_route("/api/echo", api_echo, methods=["POST"])
    app.add_middleware(BaseHTTPMiddleware, dispatch=print_incoming_request)
    return app


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local MCP and HTTP request echo service.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", default=8765, type=int, help="Bind port (default: 8765)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_arguments(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
