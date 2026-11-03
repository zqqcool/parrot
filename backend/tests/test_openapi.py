from pathlib import Path

from app.core.config import load_app_config
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_openapi_exposes_cookie_auth_without_http_im_entry() -> None:
    schema = create_app(load_app_config(ROOT / "config" / "dev.toml")).openapi()
    paths = schema["paths"]

    assert "/api/v1/auth/session" in paths
    assert "/api/v1/public/agents/{slug}/entries/text/interactions" not in paths
    assert "/api/v1/public/interactions/{interaction_id}" not in paths
    assert "/api/v1/public/agents/{slug}/channels" in paths
    list_parameters = paths["/api/v1/public/agents"]["get"]["parameters"]
    assert {item["name"] for item in list_parameters} == {"offset", "limit", "search"}
    assert next(item for item in list_parameters if item["name"] == "limit")["schema"] == {
        "type": "integer",
        "maximum": 100,
        "minimum": 1,
        "default": 10,
        "title": "Limit",
    }
    assert not any("access_token" in str(path).lower() for path in paths.values())


def test_openapi_exposes_iam_administration() -> None:
    paths = create_app(load_app_config(ROOT / "config" / "dev.toml")).openapi()["paths"]

    assert "/api/v1/admin/tenants/{tenant_id}/users" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/groups/{group_id}/roles" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/users/{user_id}/roles" in paths
    assert "/api/v1/admin/agent-types" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/subagents" not in paths
    assert "/api/v1/admin/tenants/{tenant_id}/im/channels" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/im/channel-types" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/im/agent-bindings" in paths


def test_openapi_exposes_qiniu_managed_agent_avatar_uploads() -> None:
    paths = create_app(load_app_config(ROOT / "config" / "dev.toml")).openapi()["paths"]

    admin_avatar = "/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/avatar"
    assert set(paths[admin_avatar]) == {"get", "put"}
    grant = "/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/avatar-upload-grant"
    assert set(paths[grant]) == {"post"}
    assert "application/json" in paths[grant]["post"]["requestBody"]["content"]


def test_openapi_exposes_qiniu_managed_user_avatar_uploads() -> None:
    paths = create_app(load_app_config(ROOT / "config" / "dev.toml")).openapi()["paths"]

    avatar = "/api/v1/admin/tenants/{tenant_id}/users/{user_id}/avatar"
    assert set(paths[avatar]) == {"get", "put"}
    grant = "/api/v1/admin/tenants/{tenant_id}/users/{user_id}/avatar-upload-grant"
    assert set(paths[grant]) == {"post"}
    assert "application/json" in paths[grant]["post"]["requestBody"]["content"]
    assert "/api/v1/public/agents/{slug}/avatar" in paths


def test_openapi_exposes_integrated_operations_modules() -> None:
    paths = create_app(load_app_config(ROOT / "config" / "dev.toml")).openapi()["paths"]

    assert "/api/v1/admin/tenants/{tenant_id}/runs" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/runs/requesters" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/runs/conversations" in paths
    assert (
        "/api/v1/admin/tenants/{tenant_id}/runs/conversations/{conversation_id}/messages" in paths
    )
    assert "/api/v1/admin/tenants/{tenant_id}/runs/{run_id}/task-board" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/runs/{run_id}/events" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/runs/{run_id}/diagnostic-traces" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/memory" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/memory/{memory_id}/archive" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/schedules" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/schedules/{schedule_id}/run-now" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/schedules/{schedule_id}/executions" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/skills/import" in paths
    assert set(paths["/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}"]) == {"delete", "patch"}
    assert "/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}/versions" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}:rollback" in paths
    assert "/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}/draft/files/content" in paths
    assert "/api/v1/admin/system/skills" not in paths
    assert "/api/v1/admin/system/mcp-servers" not in paths
    run_parameters = paths["/api/v1/admin/tenants/{tenant_id}/runs"]["get"]["parameters"]
    assert next(item for item in run_parameters if item["name"] == "limit")["schema"] == {
        "type": "integer",
        "maximum": 100,
        "minimum": 1,
        "default": 10,
        "title": "Limit",
    }
    assert {item["name"] for item in run_parameters} >= {"actor_type", "actor_id"}


def test_openapi_exposes_backend_query_for_every_admin_search_list() -> None:
    paths = create_app(load_app_config(ROOT / "config" / "dev.toml")).openapi()["paths"]
    search_paths = (
        "/api/v1/admin/tenants",
        "/api/v1/admin/tenants/{tenant_id}/users",
        "/api/v1/admin/tenants/{tenant_id}/groups",
        "/api/v1/admin/tenants/{tenant_id}/roles",
        "/api/v1/admin/tenants/{tenant_id}/agents",
        "/api/v1/admin/tenants/{tenant_id}/knowledge/spaces",
        "/api/v1/admin/tenants/{tenant_id}/knowledge/spaces/{space_id}/documents",
        "/api/v1/admin/tenants/{tenant_id}/llm-configs",
        "/api/v1/admin/tenants/{tenant_id}/skills",
        "/api/v1/admin/tenants/{tenant_id}/mcp-servers",
        "/api/v1/admin/tenants/{tenant_id}/runs/requesters",
        "/api/v1/admin/tenants/{tenant_id}/memory",
        "/api/v1/admin/tenants/{tenant_id}/schedules",
        "/api/v1/admin/tenants/{tenant_id}/audit-logs",
    )

    for path in search_paths:
        parameters = paths[path]["get"]["parameters"]
        query = next(item for item in parameters if item["name"] == "query")
        string_schema = next(item for item in query["schema"]["anyOf"] if item["type"] == "string")
        assert string_schema["maxLength"] == 300, path


def test_openapi_marks_provider_credentials_write_only() -> None:
    schema = create_app(load_app_config(ROOT / "config" / "dev.toml")).openapi()
    components = schema["components"]["schemas"]

    assert components["LlmConfigCreateRequest"]["properties"]["api_key"]["writeOnly"] is True
    assert components["EmbeddingConfigCreateRequest"]["properties"]["api_key"]["writeOnly"] is True
    assert components["RerankerConfigCreateRequest"]["properties"]["api_key"]["writeOnly"] is True
    assert (
        components["RerankerConfigCreateRequest"]["properties"]["access_key_id"]["writeOnly"]
        is True
    )
    assert (
        components["RerankerConfigCreateRequest"]["properties"]["secret_access_key"]["writeOnly"]
        is True
    )
    for request in (
        "LlmConfigConnectionTestRequest",
        "EmbeddingConfigConnectionTestRequest",
        "RerankerConfigConnectionTestRequest",
    ):
        credential = components[request]["properties"]["api_key"]
        assert credential["anyOf"][0]["writeOnly"] is True
    for request in (
        "RerankerConfigCreateRequest",
        "RerankerConfigUpdateRequest",
        "RerankerConfigConnectionTestRequest",
    ):
        for field in ("api_key", "access_key_id", "secret_access_key"):
            credential = components[request]["properties"][field]
            assert credential["anyOf"][0]["writeOnly"] is True
    assert components["McpCredentialCreate"]["properties"]["secret"]["writeOnly"] is True
    assert "api_key" not in components["LlmConfigView"]["properties"]
    assert "api_key" not in components["EmbeddingConfigView"]["properties"]
    assert "api_key" not in components["RerankerConfigView"]["properties"]
    assert "secret" not in components["McpCredentialView"]["properties"]


def test_openapi_exposes_knowledge_retrieval_model_configuration_and_tool_test() -> None:
    paths = create_app(load_app_config(ROOT / "config" / "dev.toml")).openapi()["paths"]
    tenant = "/api/v1/admin/tenants/{tenant_id}"

    assert set(paths[f"{tenant}/embedding-configs"]) == {"get", "post"}
    assert set(paths[f"{tenant}/embedding-configs/{{config_id}}"]) == {"delete", "patch"}
    assert set(paths[f"{tenant}/embedding-configs/{{config_id}}/connection-test"]) == {"post"}
    assert set(paths[f"{tenant}/embedding-configs/connection-test"]) == {"post"}
    assert set(paths[f"{tenant}/reranker-configs"]) == {"get", "post"}
    assert set(paths[f"{tenant}/reranker-configs/{{config_id}}"]) == {"patch"}
    assert set(paths[f"{tenant}/reranker-configs/{{config_id}}/connection-test"]) == {"post"}
    assert set(paths[f"{tenant}/reranker-configs/connection-test"]) == {"post"}
    assert set(paths[f"{tenant}/llm-configs/{{config_id}}/connection-test"]) == {"post"}
    assert set(paths[f"{tenant}/llm-configs/connection-test"]) == {"post"}
    assert set(paths[f"{tenant}/model-providers"]) == {"get"}
    for path in (
        f"{tenant}/llm-configs/{{config_id}}/connection-test",
        f"{tenant}/embedding-configs/{{config_id}}/connection-test",
        f"{tenant}/reranker-configs/{{config_id}}/connection-test",
    ):
        assert "requestBody" not in paths[path]["post"]
    for path in (
        f"{tenant}/llm-configs/connection-test",
        f"{tenant}/embedding-configs/connection-test",
        f"{tenant}/reranker-configs/connection-test",
    ):
        assert "requestBody" in paths[path]["post"]
    assert set(paths[f"{tenant}/knowledge/spaces/{{space_id}}/retrieval"]) == {"patch"}
    assert set(paths[f"{tenant}/knowledge/spaces/{{space_id}}/agents"]) == {"get"}
    merge_settings = paths[f"{tenant}/knowledge/merge-settings"]
    assert set(merge_settings) == {"get", "put"}
    merge_update_headers = {
        item["name"] for item in merge_settings["put"]["parameters"] if item["in"] == "header"
    }
    assert {"X-CSRF-Token", "Origin"} <= merge_update_headers
    assert set(paths[f"{tenant}/knowledge/documents/{{document_id}}/text-versions"]) == {"post"}
    assert set(paths[f"{tenant}/agents/{{agent_id}}/knowledge-search-test"]) == {"post"}


def test_openapi_exposes_guarded_knowledge_space_deletion() -> None:
    paths = create_app(load_app_config(ROOT / "config" / "dev.toml")).openapi()["paths"]
    path = "/api/v1/admin/tenants/{tenant_id}/knowledge/spaces/{space_id}"

    assert set(paths[path]) == {"delete"}


def test_openapi_keeps_agent_system_prompts_out_of_public_responses() -> None:
    schema = create_app(load_app_config(ROOT / "config" / "dev.toml")).openapi()
    components = schema["components"]["schemas"]

    assert "system_prompt" not in components["AgentView"]["properties"]
    assert "capability_relevance_threshold" not in components["AgentView"]["properties"]
    assert "system_prompt" in components["AgentAdminView"]["properties"]
    assert "capability_relevance_threshold" in components["AgentAdminView"]["properties"]
    assert "capability_relevance_threshold" in components["AgentUpdateRequest"]["properties"]
    assert "relevance_threshold" in components["AgentSkillRecallRequest"]["properties"]
    assert "relevance_threshold" in components["AgentMcpToolRecallRequest"]["properties"]
    recall_path = "/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/mcp-tools:search"
    assert set(schema["paths"][recall_path]) == {"post"}
