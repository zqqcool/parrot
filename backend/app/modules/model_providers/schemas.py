from typing import Literal

from pydantic import BaseModel


class ModelProviderCapabilityView(BaseModel):
    kind: Literal["llm", "embedding", "reranker"]
    description: str
    credential_type: Literal["api_key", "access_key_pair"]
    default_base_url: str | None
    default_model: str | None
    default_embedding_dimension: int | None
    base_url_placeholder: str | None
    model_placeholder: str | None


class ModelProviderView(BaseModel):
    key: str
    name: str
    capabilities: list[ModelProviderCapabilityView]
