from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

import typer
import uvicorn
from alembic.config import Config

from alembic import command
from app.core.config import AppConfig, load_app_config
from app.core.observability import configure_logging
from app.infrastructure.db.session import DatabaseManager
from app.main import create_app
from app.modules.bootstrap import bootstrap_platform, sync_permission_catalog
from app.modules.interactions.runtime_factory import (
    build_knowledge_runtime,
)
from app.modules.knowledge.evaluation import (
    KnowledgeEvaluationReport,
    evaluate_retrieval,
    load_evaluation_cases,
)
from app.modules.runs.legacy_cleanup import LegacyRunCleanupService
from app.modules.taskiq_runtime import backfill_taskiq_delivery

cli = typer.Typer(no_args_is_help=True, help="Parrot platform administration")


@cli.command()
def serve(
    config: Path = typer.Option(..., exists=True, readable=True, help="Explicit TOML config path"),
) -> None:
    settings = _load_settings(config)
    if settings.server.reload:
        raise typer.BadParameter(
            "server.reload must remain false; use the repository backend-dev command for reload"
        )
    uvicorn.run(
        create_app(settings),
        host=settings.server.host,
        port=settings.server.port,
        log_config=None,
        log_level=settings.logging.level.lower(),
        access_log=True,
    )


@cli.command("db-upgrade")
def db_upgrade(
    config: Path = typer.Option(..., exists=True, readable=True, help="Explicit TOML config path"),
) -> None:
    _load_settings(config)
    alembic_config = _alembic_config(config)
    command.upgrade(alembic_config, "head")


@cli.command("sync-permissions")
def sync_permissions(
    config: Path = typer.Option(..., exists=True, readable=True, help="Explicit TOML config path"),
) -> None:
    asyncio.run(_sync_permissions(_load_settings(config)))


@cli.command("bootstrap-admin")
def bootstrap_admin(
    username: str = typer.Option("admin", help="Initial platform administrator username"),
    password_file: Path | None = typer.Option(
        None,
        exists=True,
        readable=True,
        help="Repository-external file containing the temporary password",
    ),
    config: Path = typer.Option(..., exists=True, readable=True, help="Explicit TOML config path"),
) -> None:
    password = (
        password_file.read_text(encoding="utf-8").strip()
        if password_file
        else typer.prompt("Temporary password", hide_input=True, confirmation_prompt=True)
    )
    settings = _load_settings(config)
    if len(password) < settings.security.password_min_length:
        raise typer.BadParameter("Temporary password does not meet the configured policy")
    asyncio.run(_bootstrap_admin(settings, username, password))


@cli.command("taskiq-backfill")
def taskiq_backfill(
    config: Path = typer.Option(..., exists=True, readable=True, help="Explicit TOML config path"),
) -> None:
    """One-time migration delivery for records created before TaskIQ activation."""
    totals = asyncio.run(backfill_taskiq_delivery(_load_settings(config)))
    typer.echo(json.dumps(totals, sort_keys=True))


@cli.command("knowledge-evaluate")
def knowledge_evaluate(
    dataset: Path = typer.Option(..., exists=True, readable=True, help="Gold-set JSONL file"),
    tenant_id: str = typer.Option(..., help="Tenant that owns the evaluation Agent"),
    agent_id: str = typer.Option(..., help="Published knowledge Agent ID"),
    config: Path = typer.Option(..., exists=True, readable=True, help="Explicit TOML config path"),
) -> None:
    """Measure Recall@k and MRR without printing questions or evidence content."""
    if not tenant_id.strip() or not agent_id.strip():
        raise typer.BadParameter("tenant-id and agent-id must be non-empty")
    settings = _load_settings(config)
    database = DatabaseManager(settings.database)

    async def run() -> KnowledgeEvaluationReport:
        try:
            return await evaluate_retrieval(
                build_knowledge_runtime(settings, database),
                tenant_id,
                agent_id,
                load_evaluation_cases(dataset),
            )
        finally:
            await database.dispose()

    report = asyncio.run(run())
    typer.echo(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))


@cli.command("purge-legacy-chat-runs")
def purge_legacy_chat_runs(
    config: Path = typer.Option(..., exists=True, readable=True, help="Explicit TOML config path"),
    confirm: bool = typer.Option(False, help="Delete eligible legacy runs instead of dry-running"),
) -> None:
    """Remove legacy terminal WebSocket chats that have no durable transcript."""
    summaries = asyncio.run(_purge_legacy_chat_runs(_load_settings(config), confirm))
    typer.echo(
        json.dumps(
            {"mode": "delete" if confirm else "dry-run", "tenants": summaries},
            ensure_ascii=False,
            sort_keys=True,
        )
    )


async def _sync_permissions(settings: AppConfig) -> None:
    database = DatabaseManager(settings.database)
    try:
        async with database.platform_session() as session:
            await sync_permission_catalog(session)
    finally:
        await database.dispose()


async def _bootstrap_admin(settings: AppConfig, username: str, password: str) -> None:
    database = DatabaseManager(settings.database)
    try:
        async with database.platform_session() as session:
            await bootstrap_platform(session, username, password)
    finally:
        await database.dispose()


async def _purge_legacy_chat_runs(settings: AppConfig, confirm: bool) -> list[dict[str, object]]:
    database = DatabaseManager(settings.database)
    try:
        summaries = await LegacyRunCleanupService(database).run(confirm=confirm)
        return [asdict(summary) for summary in summaries]
    finally:
        await database.dispose()


def _alembic_config(config_path: Path) -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(backend_root / "alembic.ini"))
    alembic_config.set_main_option("parrot_config", str(config_path.resolve()))
    return alembic_config


def _load_settings(config_path: Path) -> AppConfig:
    settings = load_app_config(config_path)
    configure_logging(settings.logging)
    return settings


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
