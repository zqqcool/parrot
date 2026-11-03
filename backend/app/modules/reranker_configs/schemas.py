from pydantic import BaseModel, Field, SecretStr, model_validator


class RerankerConfigView(BaseModel):
    id: str
    tenant_id: str
    name: str
    provider: str
    model: str
    base_url: str
    credential_configured: bool
    status: str


class RerankerConfigCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64, pattern="^[a-z0-9_-]+$")
    model: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1, max_length=512)
    api_key: SecretStr | None = Field(
        default=None, min_length=1, max_length=8192, json_schema_extra={"writeOnly": True}
    )
    access_key_id: SecretStr | None = Field(
        default=None, min_length=1, max_length=256, json_schema_extra={"writeOnly": True}
    )
    secret_access_key: SecretStr | None = Field(
        default=None, min_length=1, max_length=512, json_schema_extra={"writeOnly": True}
    )

    @model_validator(mode="after")
    def validates_access_key_pair(self) -> "RerankerConfigCreateRequest":
        _validate_access_key_pair(self.access_key_id, self.secret_access_key)
        return self


class RerankerConfigUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    provider: str | None = Field(default=None, min_length=1, max_length=64, pattern="^[a-z0-9_-]+$")
    model: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, min_length=1, max_length=512)
    api_key: SecretStr | None = Field(
        default=None, min_length=1, max_length=8192, json_schema_extra={"writeOnly": True}
    )
    access_key_id: SecretStr | None = Field(
        default=None, min_length=1, max_length=256, json_schema_extra={"writeOnly": True}
    )
    secret_access_key: SecretStr | None = Field(
        default=None, min_length=1, max_length=512, json_schema_extra={"writeOnly": True}
    )
    status: str | None = Field(default=None, pattern="^(active|disabled)$")

    @model_validator(mode="after")
    def requires_change(self) -> "RerankerConfigUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        _validate_access_key_pair(self.access_key_id, self.secret_access_key)
        return self


class RerankerConfigConnectionTestRequest(BaseModel):
    config_id: str | None = Field(default=None, min_length=1, max_length=64)
    provider: str = Field(min_length=1, max_length=64, pattern="^[a-z0-9_-]+$")
    model: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1, max_length=512)
    api_key: SecretStr | None = Field(
        default=None, min_length=1, max_length=8192, json_schema_extra={"writeOnly": True}
    )
    access_key_id: SecretStr | None = Field(
        default=None, min_length=1, max_length=256, json_schema_extra={"writeOnly": True}
    )
    secret_access_key: SecretStr | None = Field(
        default=None, min_length=1, max_length=512, json_schema_extra={"writeOnly": True}
    )

    @model_validator(mode="after")
    def requires_credential_source(self) -> "RerankerConfigConnectionTestRequest":
        _validate_access_key_pair(self.access_key_id, self.secret_access_key)
        if (
            self.api_key is None
            and self.access_key_id is None
            and self.secret_access_key is None
            and self.config_id is None
        ):
            raise ValueError("credentials are required for an unsaved config")
        return self


def _validate_access_key_pair(
    access_key_id: SecretStr | None, secret_access_key: SecretStr | None
) -> None:
    if (access_key_id is None) != (secret_access_key is None):
        raise ValueError("access_key_id and secret_access_key must be provided together")
