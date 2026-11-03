from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import build_api_router
from app.core.config import AppConfig
from app.core.errors import register_exception_handlers
from app.core.middleware import register_middleware
from app.core.observability import configure_logging
from app.infrastructure.credential_cipher import CredentialCipher
from app.infrastructure.db.session import DatabaseManager
from app.infrastructure.qiniu_object_storage import QiniuObjectStorage
from app.infrastructure.redis import RedisManager
from app.modules.capability_index.hybrid_search import SystemCapabilityHybridSearch
from app.modules.interactions.runtime_factory import build_runtime
from app.modules.memory.semantic_search import build_memory_semantic_search
from app.modules.taskiq_runtime import TaskiqRuntime


def create_app(settings: AppConfig) -> FastAPI:
    configure_logging(settings.logging)
    database = DatabaseManager(settings.database)
    redis = RedisManager(settings.redis)
    taskiq = TaskiqRuntime(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        yield
        await taskiq.close()
        await redis.close()
        await database.dispose()

    app = FastAPI(
        title=settings.app.name,
        debug=settings.app.debug,
        version="0.2.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.credential_cipher = CredentialCipher(
        settings.security.credential_encryption_key.get_secret_value()
    )
    app.state.database = database
    app.state.redis = redis
    app.state.task_dispatcher = taskiq.queue
    app.state.runtime = build_runtime(settings, taskiq.queue)
    app.state.capability_search = SystemCapabilityHybridSearch(settings)
    app.state.memory_semantic_search = build_memory_semantic_search(settings)
    app.state.object_storage = QiniuObjectStorage(settings.object_storage)
    register_middleware(app)
    register_exception_handlers(app)
    app.include_router(build_api_router(), prefix=settings.api.prefix)
    return app
