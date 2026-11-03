from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.catalog import AgentCatalog


class TupleRows:
    def tuples(self) -> TupleRows:
        return self

    def all(self) -> list[tuple[str, str]]:
        return [("agent_first", "First agent"), ("agent_second", "Second agent")]

    def keys(self) -> tuple[str, str]:
        return ("id", "name")

    def __getitem__(self, _key: object) -> object:
        raise AssertionError("SQLAlchemy result rows must not be passed directly to dict()")


@pytest.mark.asyncio
async def test_agent_catalog_materializes_tuple_rows_before_building_a_name_map() -> None:
    session = SimpleNamespace(execute=AsyncMock(return_value=TupleRows()))
    catalog = AgentCatalog(cast(AsyncSession, session))

    names = await catalog.names("tenant_test", ("agent_first", "agent_second"))

    assert names == {"agent_first": "First agent", "agent_second": "Second agent"}
