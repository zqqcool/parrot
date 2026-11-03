from __future__ import annotations

import asyncio
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import load_app_config
from app.infrastructure.db.base import Base
from app.modules import models as _models  # noqa: F401

if not _models.__all__:
    raise RuntimeError("Database model registry is empty")

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

config_path = config.get_main_option("parrot_config")
if not config_path:
    raise RuntimeError("Alembic requires the parrot_config option")

settings = load_app_config(Path(config_path))
config.set_main_option("sqlalchemy.url", settings.database.migration_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database.migration_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_sync_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(run_sync_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
