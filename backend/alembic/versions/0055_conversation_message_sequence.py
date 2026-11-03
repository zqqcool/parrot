"""Allow ordered multi-message transcripts per interaction.

Revision ID: 0055_message_sequence
Revises: 0054_mcp_tool_policies
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0055_message_sequence"
down_revision: str | None = "0054_mcp_tool_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("conversation_messages", sa.Column("sequence", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE conversation_messages AS message
            SET sequence = CASE
                WHEN message.role = 'user' THEN 0
                ELSE COALESCE(
                    (
                        SELECT max(event.sequence)
                        FROM interaction_events AS event
                        WHERE event.tenant_id = message.tenant_id
                          AND event.interaction_id = message.interaction_id
                          AND event.type = 'ai.output.completed'
                          AND event.data ->> 'content' = message.content
                    ),
                    2147483647
                )
            END
            """
        )
    )
    op.alter_column("conversation_messages", "sequence", nullable=False)
    op.drop_constraint(
        "uq_conversation_message_interaction_role",
        "conversation_messages",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_conversation_message_interaction_sequence",
        "conversation_messages",
        ["tenant_id", "interaction_id", "sequence"],
    )
    _backfill_interaction_messages()


def downgrade() -> None:
    _reject_multi_role_messages()
    op.drop_constraint(
        "uq_conversation_message_interaction_sequence",
        "conversation_messages",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_conversation_message_interaction_role",
        "conversation_messages",
        ["tenant_id", "interaction_id", "role"],
    )
    op.drop_column("conversation_messages", "sequence")


def _reject_multi_role_messages() -> None:
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT count(*)
            FROM (
                SELECT tenant_id, interaction_id, role
                FROM conversation_messages
                GROUP BY tenant_id, interaction_id, role
                HAVING count(*) > 1
            ) AS duplicate_roles
            """
            )
        )
        .scalar_one()
    )
    if int(duplicates):
        raise RuntimeError(
            "Conversation message sequence downgrade requires at most one message per role"
        )


def _backfill_interaction_messages() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO conversation_messages (
                id,
                tenant_id,
                interaction_id,
                sequence,
                agent_id,
                im_channel_id,
                im_agent_binding_id,
                actor_type,
                actor_id,
                conversation_id,
                role,
                direction,
                external_message_id,
                provider_message_id,
                delivery_status,
                content,
                status,
                expires_at,
                created_at,
                updated_at
            )
            SELECT
                'conversation_event_' || md5(event.id || ':' || event.type),
                event.tenant_id,
                event.interaction_id,
                event.sequence,
                interaction.agent_id,
                interaction.im_channel_id,
                interaction.im_agent_binding_id,
                interaction.actor_type,
                interaction.actor_id,
                interaction.conversation_id,
                CASE
                    WHEN event.type = 'ai.output.completed' THEN 'assistant'
                    ELSE 'user'
                END,
                CASE
                    WHEN event.type = 'ai.output.completed' THEN 'outbound'
                    ELSE 'inbound'
                END,
                NULL,
                NULL,
                'not_required',
                CASE
                    WHEN event.type = 'ai.output.completed' THEN event.data ->> 'content'
                    ELSE event.data ->> 'message'
                END,
                'active',
                interaction.transcript_expires_at,
                event.created_at,
                event.created_at
            FROM interaction_events AS event
            JOIN interactions AS interaction
              ON interaction.tenant_id = event.tenant_id
             AND interaction.id = event.interaction_id
            WHERE interaction.runtime_depth = 0
              AND interaction.entry_type <> 'schedule'
              AND interaction.conversation_id IS NOT NULL
              AND (
                  (
                      event.type = 'ai.output.completed'
                      AND event.data ->> 'runtime_status' = 'waiting_user_input'
                      AND nullif(btrim(event.data ->> 'content'), '') IS NOT NULL
                  )
                  OR (
                      event.type = 'ai.interaction.steer.requested'
                      AND nullif(btrim(event.data ->> 'message'), '') IS NOT NULL
                  )
              )
            ON CONFLICT (tenant_id, interaction_id, sequence) DO NOTHING
            """
        )
    )
