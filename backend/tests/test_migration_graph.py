from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
MAX_ALEMBIC_VERSION_LENGTH = 32


def test_migration_graph_has_one_short_head_revision() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    revisions = list(scripts.walk_revisions())

    assert len(scripts.get_heads()) == 1
    assert all(len(revision.revision) <= MAX_ALEMBIC_VERSION_LENGTH for revision in revisions)


def test_agent_mcp_binding_migration_adds_its_composite_fk_target_constraint() -> None:
    migration = ROOT / "alembic/versions/0017_agent_mcp_bindings.py"

    assert (
        'op.create_unique_constraint("uq_mcp_server_tenant_id", "mcp_servers", ["tenant_id", "id"])'
        in migration.read_text(encoding="utf-8")
    )


def test_memory_index_migration_adds_its_composite_fk_target_constraint() -> None:
    migration = ROOT / "alembic/versions/0019_memory_vector_indexing.py"
    expected_constraint = (
        'op.create_unique_constraint("uq_memory_record_tenant_id", "memory_records", '
        '["tenant_id", "id"])'
    )

    assert expected_constraint in migration.read_text(encoding="utf-8")


def test_p2p_only_migration_rejects_legacy_group_and_thread_data() -> None:
    migration = ROOT / "alembic/versions/0045_p2p_only_conversations.py"
    source = migration.read_text(encoding="utf-8")

    assert "def _reject_legacy_conversation_data()" in source
    assert "conversation_kind <> 'p2p'" in source
    assert "thread_id IS NOT NULL OR scope_type = 'thread'" in source
    assert "memory_type = 'thread_summary'" in source
    assert "P2P-only migration blocked by legacy group or thread data" in source


def test_p2p_only_migration_drops_legacy_columns_and_rebuilds_p2p_indexes() -> None:
    migration = ROOT / "alembic/versions/0045_p2p_only_conversations.py"
    source = migration.read_text(encoding="utf-8")

    for statement in (
        'op.drop_column("interactions", "conversation_kind")',
        'op.drop_column("interactions", "thread_id")',
        'op.drop_column("conversation_messages", "conversation_kind")',
        'op.drop_column("conversation_messages", "thread_id")',
        'op.drop_column("memory_records", "thread_id")',
    ):
        assert statement in source
    assert '"ix_conversation_message_history"' in source
    assert '"ix_conversation_message_channel_history"' in source


def test_knowledge_title_identity_migration_uses_correlated_backfill_lookups() -> None:
    migration = ROOT / "alembic/versions/0047_knowledge_document_title_identity.py"
    source = migration.read_text(encoding="utf-8")

    assert "SELECT source.created_by_user_id" in source
    assert "SELECT document.created_by_user_id" in source
    assert "LEFT JOIN knowledge_sources AS source" not in source


def test_knowledge_index_reconcile_migration_scopes_statuses_to_each_space() -> None:
    migration = ROOT / "alembic/versions/0058_knowledge_index_reconcile.py"
    source = migration.read_text(encoding="utf-8")

    assert "document.space_id = space.id" in source
    assert "job.embedding_config_id = space.embedding_config_id" in source
    assert "job.index_revision = space.retrieval_index_revision" in source
    assert "bool_or(job.status = 'failed')" in source
    assert "bool_or(job.status IN ('queued', 'running'))" in source


def test_knowledge_merge_settings_migration_enforces_policy_invariants() -> None:
    migration = ROOT / "alembic/versions/0060_knowledge_merge_settings.py"
    source = migration.read_text(encoding="utf-8")

    for constraint in (
        "ck_knowledge_merge_settings_rerank_top_n",
        "ck_knowledge_merge_settings_result_top_k",
        "ck_knowledge_merge_settings_top_n_gte_top_k",
        "ck_knowledge_merge_settings_min_score",
        "ck_knowledge_merge_settings_reranker_dependency",
        "ck_knowledge_merge_settings_score_dependency",
    ):
        assert constraint in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))" in source
