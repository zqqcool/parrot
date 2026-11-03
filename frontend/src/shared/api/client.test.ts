import { afterEach, describe, expect, it, vi } from "vitest";

import { adminApi, http } from "./client";

const search = "Alpha & Beta";

describe("adminApi server search", () => {
  afterEach(() => vi.restoreAllMocks());

  it.each([
    ["tenants", () => adminApi.listTenants(search), "/api/v1/admin/tenants"],
    ["users", () => adminApi.listUsers("tenant_test", search), "/users"],
    ["groups", () => adminApi.listGroups("tenant_test", search), "/groups"],
    ["roles", () => adminApi.listRoles("tenant_test", search), "/roles"],
    ["agents", () => adminApi.listAgents("tenant_test", search), "/agents"],
    [
      "knowledge spaces",
      () => adminApi.listKnowledgeSpaces("tenant_test", search),
      "/knowledge/spaces",
    ],
    [
      "knowledge documents",
      () => adminApi.listKnowledgeDocuments("tenant_test", "space_test", search),
      "/knowledge/spaces/space_test/documents",
    ],
    ["LLM configs", () => adminApi.listLlmConfigs("tenant_test", search), "/llm-configs"],
    ["skills", () => adminApi.listSkills("tenant_test", search), "/skills"],
    ["MCP servers", () => adminApi.listMcpServers("tenant_test", search), "/mcp-servers"],
    ["memory", () => adminApi.listMemory("tenant_test", search), "/memory"],
    ["schedules", () => adminApi.listSchedules("tenant_test", search), "/schedules"],
    ["audit", () => adminApi.listAudit("tenant_test", search), "/audit-logs"],
  ])("sends %s search terms to the backend", async (_name, invoke, path) => {
    const get = vi.spyOn(http, "get").mockResolvedValue([]);

    await invoke();

    expect(get).toHaveBeenCalledWith(expect.stringContaining(path));
    expect(get).toHaveBeenCalledWith(expect.stringContaining("query=Alpha+%26+Beta"));
  });

  it("sends requester text and identity filters before the backend limit", async () => {
    const get = vi.spyOn(http, "get").mockResolvedValue([]);

    await adminApi.listRunRequesters("tenant_test", { actorType: "user", query: search });

    expect(get).toHaveBeenCalledWith(
      "/api/v1/admin/tenants/tenant_test/runs/requesters?limit=100&actor_type=user&query=Alpha+%26+Beta",
    );
  });

  it("uses the Agent memory-view endpoint with context, paging, and an optional keyword", async () => {
    const get = vi
      .spyOn(http, "get")
      .mockResolvedValue({ items: [], total: 0, offset: 0, limit: 20 });

    await adminApi.searchAgentMemory("tenant_test", {
      agentId: "agent_test",
      actorId: "user_test",
      query: search,
      offset: 20,
      limit: 50,
    });

    expect(get).toHaveBeenCalledWith(
      "/api/v1/admin/tenants/tenant_test/memory/agent-view?agent_id=agent_test&offset=20&limit=50&actor_id=user_test&query=Alpha+%26+Beta",
    );
  });

  it("sends typed draft fields to the modal LLM connection-test endpoint", async () => {
    const post = vi.spyOn(http, "post").mockResolvedValue({ connected: true });
    const payload = {
      provider: "volcengine_ark",
      model: "doubao-seed-2-0-mini-260215",
      base_url: "https://ark.cn-beijing.volces.com/api/v3",
      api_key: "secret",
      temperature: 0.2,
      max_tokens: 4096,
      thinking_enabled: false,
      prompt_cache_enabled: false,
    };

    await adminApi.testLlmConfigDraftConnection("tenant_test", payload);

    expect(post).toHaveBeenCalledWith(
      "/api/v1/admin/tenants/tenant_test/llm-configs/connection-test",
      payload,
      { timeoutMs: 35_000 },
    );
  });
});
