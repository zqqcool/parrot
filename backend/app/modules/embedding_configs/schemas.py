from pydantic import BaseModel, Field, SecretStr, model_validator


class EmbeddingConfigView(BaseModel):
    id: str
    tenant_id: str
    name: str
    provider: str
    model: str
    base_url: str
    credential_configured: bool
    embedding_dimension: int
    configuration_version: int
    status: str
    reference_count: int
    can_delete: bool


class EmbeddingConfigCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    provider: str = Field(default="openai", min_length=1, max_length=64, pattern="^[a-z0-9_-]+$")
    model: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1, max_length=512)
    api_key: SecretStr = Field(min_length=1, max_length=8192)
    embedding_dimension: int = Field(ge=8, le=16_384)


class EmbeddingConfigUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    provider: str | None = Field(default=None, min_length=1, max_length=64, pattern="^[a-z0-9_-]+$")
    model: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, min_length=1, max_length=512)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=8192)
    embedding_dimension: int | None = Field(default=None, ge=8, le=16_384)
    status: str | None = Field(default=None, pattern="^(active|disabled)$")

    @model_validator(mode="after")
    def requires_change(self) -> "EmbeddingConfigUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class EmbeddingConfigConnectionTestRequest(BaseModel):
    config_id: str | None = Field(default=None, min_length=1, max_length=64)
    provider: str = Field(min_length=1, max_length=64, pattern="^[a-z0-9_-]+$")
    model: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1, max_length=512)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=8192)
    embedding_dimension: int = Field(ge=8, le=16_384)

    @model_validator(mode="after")
    def requires_credential_source(self) -> "EmbeddingConfigConnectionTestRequest":
        if self.api_key is None and self.config_id is None:
            raise ValueError("api_key is required for an unsaved config")
        return self
