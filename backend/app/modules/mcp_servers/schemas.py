from typing import Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, Field, SecretStr, model_validator

from app.modules.iam.schemas import UserReference


class McpBoundAgentView(BaseModel):
    id: str
    name: str


class McpCredentialCreate(BaseModel):
    target: Literal["env", "header"] = "env"
    name: str = Field(pattern="^[A-Za-z][A-Za-z0-9_-]{0,127}$")
    secret: SecretStr = Field(min_length=1, max_length=8192)


class McpCredentialUpdate(BaseModel):
    target: Literal["env", "header"] = "env"
    name: str = Field(pattern="^[A-Za-z][A-Za-z0-9_-]{0,127}$")
    secret: SecretStr | None = Field(default=None, min_length=1, max_length=8192)


class McpCredentialView(BaseModel):
    target: Literal["env", "header"]
    name: str
    configured: bool = True


class McpToolPolicyInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2_000)
    input_schema: dict[str, object]
    effect: Literal["read", "side_effect"]
    approval: Literal["automatic", "required", "forbidden"]
    parallel_safe: bool = False

    @model_validator(mode="after")
    def validate_automatic_effect(self) -> "McpToolPolicyInput":
        if self.approval == "automatic" and self.effect != "read":
            raise ValueError("Only read-only MCP tools can be automatic")
        if self.parallel_safe and (self.effect, self.approval) != ("read", "automatic"):
            raise ValueError("Only automatic read-only MCP tools can be parallel-safe")
        try:
            Draft202012Validator.check_schema(self.input_schema)
        except SchemaError as error:
            raise ValueError("MCP tool input_schema must be valid JSON Schema") from error
        return self


class McpToolPolicyView(McpToolPolicyInput):
    schema_hash: str


class McpDiscoveredToolView(BaseModel):
    name: str
    description: str
    input_schema: dict[str, object]
    schema_hash: str
    read_only_hint: bool


class McpServerView(BaseModel):
    id: str
    tenant_id: str
    created_by_user: UserReference | None = None
    name: str
    transport: str
    endpoint: str
    arguments: list[str]
    credentials: list[McpCredentialView]
    status: str
    tool_policies: list[McpToolPolicyView]
    bound_agents: tuple[McpBoundAgentView, ...] | None = None


class McpServerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    transport: str = Field(pattern="^(stdio|sse|streamable_http)$")
    endpoint: str = Field(min_length=1, max_length=512)
    arguments: list[str] = Field(default_factory=list[str], max_length=64)
    credentials: list[McpCredentialCreate] = Field(default_factory=list[McpCredentialCreate])
    tool_policies: list[McpToolPolicyInput] = Field(
        default_factory=list[McpToolPolicyInput], max_length=128
    )

    @model_validator(mode="after")
    def validate_unique_tool_policies(self) -> "McpServerCreateRequest":
        _validate_unique_policy_names(self.tool_policies)
        return self


class McpServerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    transport: str | None = Field(default=None, pattern="^(stdio|sse|streamable_http)$")
    endpoint: str | None = Field(default=None, min_length=1, max_length=512)
    arguments: list[str] | None = Field(default=None, max_length=64)
    credentials: list[McpCredentialUpdate] | None = None
    status: str | None = Field(default=None, pattern="^(active|disabled)$")
    tool_policies: list[McpToolPolicyInput] | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_unique_tool_policies(self) -> "McpServerUpdateRequest":
        _validate_unique_policy_names(self.tool_policies or [])
        return self


def _validate_unique_policy_names(policies: list[McpToolPolicyInput]) -> None:
    names = [policy.name for policy in policies]
    if len(names) != len(set(names)):
        raise ValueError("MCP tool policy names must be unique")
