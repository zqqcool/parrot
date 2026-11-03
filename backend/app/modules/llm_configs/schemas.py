from typing import Self

from pydantic import BaseModel, Field, SecretStr, model_validator


class LlmConfigView(BaseModel):
    id: str
    tenant_id: str
    name: str
    provider: str
    model: str
    base_url: str | None
    credential_configured: bool
    temperature: float
    max_tokens: int
    thinking_enabled: bool
    prompt_cache_enabled: bool
    status: str
    is_default: bool


class LlmConfigCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64, pattern="^[a-z0-9_-]+$")
    model: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1, max_length=512)
    api_key: SecretStr = Field(min_length=1, max_length=8192)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1, le=32768)
    thinking_enabled: bool = False
    prompt_cache_enabled: bool = False
    is_default: bool = False


class LlmConfigUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    provider: str | None = Field(default=None, min_length=1, max_length=64, pattern="^[a-z0-9_-]+$")
    model: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=512)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=8192)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32768)
    thinking_enabled: bool | None = None
    prompt_cache_enabled: bool | None = None
    status: str | None = Field(default=None, pattern="^(active|disabled)$")
    is_default: bool | None = None

    @model_validator(mode="after")
    def reject_clearing_base_url(self) -> Self:
        if "base_url" in self.model_fields_set and self.base_url is None:
            raise ValueError("base_url cannot be null")
        return self


class LlmConfigConnectionTestRequest(BaseModel):
    config_id: str | None = Field(default=None, min_length=1, max_length=64)
    provider: str = Field(min_length=1, max_length=64, pattern="^[a-z0-9_-]+$")
    model: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1, max_length=512)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=8192)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1, le=32768)
    thinking_enabled: bool = False
    prompt_cache_enabled: bool = False

    @model_validator(mode="after")
    def requires_credential_source(self) -> Self:
        if self.api_key is None and self.config_id is None:
            raise ValueError("api_key is required for an unsaved config")
        return self
