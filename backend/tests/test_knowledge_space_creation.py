from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import load_app_config
from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.ports import AgentCatalogPort
from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.schemas import (
    KnowledgeSpaceCreateRequest,
    KnowledgeSpaceRetrievalUpdateRequest,
    KnowledgeSpaceView,
    KnowledgeTextProcessingSettings,
)
from app.modules.knowledge.service import KnowledgeService

ROOT = Path(__file__).resolve().parents[1]


def principal() -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="operator",
        display_name="Operator",
        permissions=("knowledge.spaces.manage",),
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )


def space_view_stub(_item: object) -> KnowledgeSpaceView:
    return cast(KnowledgeSpaceView, SimpleNamespace())


@pytest.mark.asyncio
async def test_knowledge_space_creation_uses_its_generated_id_as_the_internal_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    service = KnowledgeService(
        cast(AsyncSession, session),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentCatalogPort, SimpleNamespace()),
        settings=_vector_settings(),
    )
    repository = SimpleNamespace(replace_grants=AsyncMock())
    service.repository = cast(KnowledgeRepository, repository)
    monkeypatch.setattr(
        "app.modules.knowledge.service.knowledge_space_view",
        space_view_stub,
    )

    await service.create_space(
        principal(),
        "tenant_test",
        KnowledgeSpaceCreateRequest(name="Engineering", slug="legacy-engineering"),
    )

    created = session.add.call_args_list[0].args[0]
    assert created.slug == created.id
    assert created.slug != "legacy-engineering"
    assert created.slug.startswith("knowledge_space_")
    repository.replace_grants.assert_awaited_once_with(
        "tenant_test", created.id, ("user_test",), ()
    )
    assert created.embedding_config_id is None
    assert created.retrieval_index_status == "not_configured"
    assert created.chunk_separator == r"\n\n"
    assert created.normalize_whitespace is False
    assert created.remove_urls_and_emails is False


@pytest.mark.asyncio
async def test_knowledge_space_creation_persists_the_selected_embedding_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    service = KnowledgeService(
        cast(AsyncSession, session),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentCatalogPort, SimpleNamespace()),
    )
    repository = SimpleNamespace(replace_grants=AsyncMock())
    service.repository = cast(KnowledgeRepository, repository)
    embedding = EmbeddingConfig(
        id="embedding_test",
        tenant_id="tenant_test",
        name="Embedding",
        provider="openai_compatible",
        model="text-embedding-3-large",
        base_url="http://127.0.0.1:11434/v1",
        embedding_dimension=1024,
        configuration_version=1,
        status="active",
    )
    validate = AsyncMock(return_value=embedding)
    monkeypatch.setattr(service, "_validate_retrieval_configs", validate)
    monkeypatch.setattr(
        "app.modules.knowledge.service.knowledge_space_view",
        space_view_stub,
    )
    payload = KnowledgeSpaceCreateRequest(
        name="Engineering",
        embedding_config_id="embedding_test",
    )

    await service.create_space(principal(), "tenant_test", payload)

    created = session.add.call_args_list[0].args[0]
    assert created.embedding_config_id == "embedding_test"
    assert created.retrieval_index_status == "pending"
    assert created.embedding_config_provider == "openai_compatible"
    assert created.embedding_config_model == "text-embedding-3-large"
    assert created.embedding_config_dimension == 1024
    assert created.embedding_config_version == 1
    validate.assert_awaited_once_with("tenant_test", payload)


@pytest.mark.asyncio
async def test_embedding_space_requires_a_configured_vector_runtime() -> None:
    configured = load_app_config(ROOT / "config" / "dev.toml")
    service = KnowledgeService(
        cast(AsyncSession, SimpleNamespace()),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentCatalogPort, SimpleNamespace()),
        settings=configured.model_copy(
            update={
                "knowledge": configured.knowledge.model_copy(
                    update={"vector": configured.knowledge.vector.model_copy(update={"uri": None})}
                )
            }
        ),
    )

    with pytest.raises(AppError) as error:
        await service._validate_retrieval_configs(  # pyright: ignore[reportPrivateUsage]
            "tenant_test",
            KnowledgeSpaceCreateRequest(name="Engineering", embedding_config_id="embedding_test"),
        )

    assert error.value.code == "KNOWLEDGE_VECTOR_RUNTIME_UNAVAILABLE"
    assert error.value.status_code == 422


def _vector_settings():
    settings = load_app_config(ROOT / "config" / "dev.toml")
    return settings.model_copy(
        update={
            "knowledge_credentials": settings.knowledge_credentials.model_copy(
                update={"values": {"milvus-root-token": "test-token"}}
            )
        }
    )


@pytest.mark.asyncio
async def test_knowledge_space_creation_persists_text_processing_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    service = KnowledgeService(
        cast(AsyncSession, session),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentCatalogPort, SimpleNamespace()),
    )
    service.repository = cast(KnowledgeRepository, SimpleNamespace(replace_grants=AsyncMock()))
    monkeypatch.setattr(
        "app.modules.knowledge.service.knowledge_space_view",
        space_view_stub,
    )

    await service.create_space(
        principal(),
        "tenant_test",
        KnowledgeSpaceCreateRequest(
            name="Engineering",
            chunk_separator="***",
            text_processing=KnowledgeTextProcessingSettings(
                normalize_whitespace=True,
                remove_urls_and_emails=True,
            ),
        ),
    )

    created = session.add.call_args_list[0].args[0]
    assert created.chunk_separator == "***"
    assert created.normalize_whitespace is True
    assert created.remove_urls_and_emails is True


@pytest.mark.asyncio
async def test_knowledge_space_retrieval_cannot_change_its_embedding_mode() -> None:
    space = SimpleNamespace(
        embedding_config_id="embedding_current",
    )
    service = KnowledgeService(
        cast(AsyncSession, SimpleNamespace()),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentCatalogPort, SimpleNamespace()),
    )
    service._accessible_space = AsyncMock(return_value=space)  # pyright: ignore[reportPrivateUsage]

    with pytest.raises(AppError) as error:
        await service.update_space_retrieval(
            principal(),
            "tenant_test",
            "space_test",
            KnowledgeSpaceRetrievalUpdateRequest(
                embedding_config_id="embedding_replacement",
            ),
        )

    assert error.value.code == "KNOWLEDGE_EMBEDDING_LOCKED"
    assert error.value.status_code == 409
