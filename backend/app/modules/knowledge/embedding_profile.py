from __future__ import annotations

from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.knowledge.models import KnowledgeSpace


def apply_embedding_snapshot(space: KnowledgeSpace, config: EmbeddingConfig) -> None:
    """Persist the model identity that defines this space's vector space."""
    space.embedding_config_provider = config.provider
    space.embedding_config_model = config.model
    space.embedding_config_base_url = config.base_url
    space.embedding_config_dimension = config.embedding_dimension
    space.embedding_config_version = config.configuration_version


def embedding_snapshot_matches(space: KnowledgeSpace, config: EmbeddingConfig) -> bool:
    if space.embedding_config_id != config.id:
        return False
    return (
        space.embedding_config_provider == config.provider
        and space.embedding_config_model == config.model
        and space.embedding_config_base_url == config.base_url
        and space.embedding_config_dimension == config.embedding_dimension
        and space.embedding_config_version == config.configuration_version
    )
