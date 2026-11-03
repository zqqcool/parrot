from typing import cast

import pytest
from sqlalchemy import ForeignKeyConstraint, Table, UniqueConstraint
from sqlalchemy.sql.schema import ColumnCollectionConstraint

from app.modules.agents.models import AgentPublication
from app.modules.im.models import ImAgentBinding, ImChannel, ImInboundDelivery
from app.modules.interactions.models import (
    ConversationMessage,
    Interaction,
    InteractionDiagnosticTrace,
)
from app.modules.memory.models import MemoryRecord
from app.modules.schedules.models import ScheduledTask, ScheduleExecution
from app.modules.tenancy.models import GroupMember, GroupRole, MembershipRole, TenantMembership


def _constraint_columns(
    table: Table, constraint_type: type[ColumnCollectionConstraint]
) -> set[tuple[str, ...]]:
    return {
        tuple(str(column.name) for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, constraint_type)
    }


def test_tenant_entities_have_composite_identity_constraints() -> None:
    assert ("tenant_id", "id") in _constraint_columns(
        cast(Table, TenantMembership.__table__), UniqueConstraint
    )
    assert ("tenant_id", "id") in _constraint_columns(
        cast(Table, AgentPublication.__table__), UniqueConstraint
    )
    assert ("tenant_id", "id") in _constraint_columns(
        cast(Table, Interaction.__table__), UniqueConstraint
    )
    assert ("tenant_id", "id") in _constraint_columns(
        cast(Table, ScheduledTask.__table__), UniqueConstraint
    )


def test_operations_tables_enforce_tenant_foreign_keys() -> None:
    for table in (
        cast(Table, InteractionDiagnosticTrace.__table__),
        cast(Table, MemoryRecord.__table__),
        cast(Table, ScheduledTask.__table__),
        cast(Table, ScheduleExecution.__table__),
        cast(Table, ImAgentBinding.__table__),
        cast(Table, ImInboundDelivery.__table__),
    ):
        foreign_keys = _constraint_columns(table, ForeignKeyConstraint)
        assert any(columns[0] == "tenant_id" for columns in foreign_keys)


def test_conversation_messages_allow_ordered_multi_turn_interactions() -> None:
    constraints = _constraint_columns(cast(Table, ConversationMessage.__table__), UniqueConstraint)

    assert ("tenant_id", "interaction_id", "sequence") in constraints
    assert ("tenant_id", "interaction_id", "role") not in constraints


def test_im_channel_records_keep_tenant_scoped_identity_and_foreign_keys() -> None:
    channels = cast(Table, ImChannel.__table__)
    deliveries = cast(Table, ImInboundDelivery.__table__)

    assert ("tenant_id", "id") in _constraint_columns(channels, UniqueConstraint)
    assert any(
        columns == ("channel_id", "visitor_id", "client_message_id")
        for columns in _constraint_columns(deliveries, UniqueConstraint)
    )


def test_schedule_interaction_link_never_nulls_tenant_identity() -> None:
    table = cast(Table, ScheduleExecution.__table__)
    interaction_fk = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and tuple(column.name for column in constraint.columns) == ("tenant_id", "interaction_id")
    )

    assert interaction_fk.ondelete is None


@pytest.mark.parametrize(
    "table",
    [
        cast(Table, GroupMember.__table__),
        cast(Table, GroupRole.__table__),
        cast(Table, MembershipRole.__table__),
    ],
)
def test_assignment_tables_enforce_composite_tenant_foreign_keys(table: Table) -> None:
    foreign_keys = _constraint_columns(table, ForeignKeyConstraint)
    assert any(columns[0] == "tenant_id" and len(columns) == 2 for columns in foreign_keys)
