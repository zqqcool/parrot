from __future__ import annotations

from typing import cast

import pytest
from starlette.routing import Route

from mcp_api_echo_demo.main import create_app, create_mcp_server, create_test_ticket, decode_payload


def test_decode_payload_handles_json_and_text() -> None:
    assert decode_payload(b'{"message":"hello"}') == {"message": "hello"}
    assert decode_payload(b"plain text") == "plain text"


@pytest.mark.asyncio
async def test_app_exposes_the_http_and_mcp_interfaces() -> None:
    app = create_app()
    server = create_mcp_server()
    tools = await server.list_tools()
    paths = {route.path for route in app.routes if isinstance(route, Route)}
    ticket = next(tool for tool in tools if tool.name == "create_ticket")
    created = await server.call_tool(
        "create_ticket",
        {
            "contact_name": "Ada",
            "contact_method": "ada@example.test",
            "city": "Shanghai",
            "business_need": "Product demo",
            "confirmed": True,
        },
    )

    assert {"/api/echo", "/mcp"} <= paths
    assert [tool.name for tool in tools] == ["echo", "create_ticket"]
    assert ticket.annotations is not None
    assert ticket.annotations.readOnlyHint is False
    assert set(ticket.inputSchema["required"]) == {
        "business_need",
        "city",
        "contact_method",
        "contact_name",
    }
    assert isinstance(created, tuple)
    structured = cast(dict[str, object], created[1])
    assert structured["status"] == "created"


def test_create_ticket_requires_complete_information_and_explicit_confirmation() -> None:
    incomplete = create_test_ticket("Ada", "ada@example.test", "", "Product demo", confirmed=True)
    unconfirmed = create_test_ticket(
        "Ada", "ada@example.test", "Shanghai", "Product demo", confirmed=False
    )

    assert incomplete == {
        "status": "rejected",
        "code": "TICKET_INPUT_INCOMPLETE",
        "missing_fields": ["city"],
    }
    assert unconfirmed["code"] == "TICKET_CONFIRMATION_REQUIRED"


def test_create_ticket_returns_only_safe_test_metadata() -> None:
    result = create_test_ticket(
        "Ada",
        "ada@example.test",
        "Shanghai",
        "Product demo",
        requested_time="Friday morning",
        confirmed=True,
    )

    assert result["status"] == "created"
    assert str(result["ticket_id"]).startswith("TEST-TICKET-")
    assert result["test_only"] is True
    assert "Ada" not in str(result)
    assert "ada@example.test" not in str(result)
