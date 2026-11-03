import { describe, expect, it } from "vitest";

import { endpoints } from "@/shared/api/endpoints";

describe("API endpoint contract", () => {
  it("substitutes and encodes OpenAPI path parameters", () => {
    expect(endpoints.public.agent("agent / one")).toBe("/api/v1/public/agents/agent%20%2F%20one");
    expect(endpoints.admin.run("tenant / one", "run / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/runs/run%20%2F%20one",
    );
    expect(endpoints.admin.runConversationMessages("tenant / one", "conversation / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/runs/conversations/conversation%20%2F%20one/messages",
    );
  });

  it("restricts schedule actions to declared OpenAPI operations", () => {
    expect(endpoints.admin.scheduleAction("tenant_one", "schedule_one", "run-now")).toBe(
      "/api/v1/admin/tenants/tenant_one/schedules/schedule_one/run-now",
    );
  });

  it("exposes agent capability bindings and channel paths from OpenAPI", () => {
    expect(endpoints.admin.agentMcpServers("tenant / one", "agent / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/agents/agent%20%2F%20one/mcp-servers",
    );
    expect(endpoints.admin.agentSkillRecall("tenant / one", "agent / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/agents/agent%20%2F%20one/skills:search",
    );
    expect(endpoints.admin.agentMcpToolRecall("tenant / one", "agent / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/agents/agent%20%2F%20one/mcp-tools:search",
    );
    expect(endpoints.admin.mcpServerDiscoverTools("tenant / one", "server / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/mcp-servers/server%20%2F%20one/discover-tools",
    );
    expect(endpoints.admin.agentImBindings("tenant / one", "agent / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/agents/agent%20%2F%20one/im-bindings",
    );
    expect(endpoints.admin.imChannelTypes("tenant / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/im/channel-types",
    );
    expect(endpoints.admin.skill("tenant / one", "skill / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/skills/skill%20%2F%20one",
    );
  });

  it("exposes tenant-scoped knowledge document paths from OpenAPI", () => {
    expect(endpoints.admin.knowledgeDocuments("tenant / one", "space / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/spaces/space%20%2F%20one/documents",
    );
    expect(endpoints.admin.knowledgeMergeSettings("tenant / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/merge-settings",
    );
    expect(endpoints.admin.knowledgeActiveIngestions("tenant / one", "space / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/spaces/space%20%2F%20one/ingestions",
    );
    expect(endpoints.admin.knowledgeDocumentArchive("tenant / one", "document / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/documents/document%20%2F%20one/archive",
    );
    expect(endpoints.admin.knowledgeDocumentUploadGrant("tenant / one", "space / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/spaces/space%20%2F%20one/document-upload-grants",
    );
    expect(
      endpoints.admin.knowledgeDocumentVersionUploadGrant("tenant / one", "document / one"),
    ).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/documents/document%20%2F%20one/version-upload-grants",
    );
    expect(endpoints.admin.knowledgeDocumentTextVersion("tenant / one", "document / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/documents/document%20%2F%20one/text-versions",
    );
    expect(
      endpoints.admin.knowledgeDocumentVersionSource(
        "tenant / one",
        "document / one",
        "version / one",
      ),
    ).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/documents/document%20%2F%20one/versions/version%20%2F%20one/source",
    );
    expect(endpoints.admin.knowledgeMediaContent("tenant / one", "media / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/media/media%20%2F%20one/content",
    );
    expect(endpoints.admin.knowledgeSourceConfirm("tenant / one", "source / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/sources/source%20%2F%20one/confirm",
    );
    expect(endpoints.admin.knowledgeSourceRetryConfirm("tenant / one", "source / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/sources/source%20%2F%20one/retry-confirm",
    );
    expect(endpoints.admin.knowledgeSourceCleanup("tenant / one", "source / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/sources/source%20%2F%20one",
    );
    expect(endpoints.admin.knowledgeSpaceChunking("tenant / one", "space / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/spaces/space%20%2F%20one/chunking",
    );
    expect(endpoints.admin.knowledgeSpaceAgents("tenant / one", "space / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/knowledge/spaces/space%20%2F%20one/agents",
    );
  });

  it("exposes provider catalog and draft model connection-test paths", () => {
    expect(endpoints.admin.modelProviders("tenant / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/model-providers",
    );
    expect(endpoints.admin.llmConfigDraftConnectionTest("tenant / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/llm-configs/connection-test",
    );
    expect(endpoints.admin.embeddingConfigDraftConnectionTest("tenant / one")).toBe(
      "/api/v1/admin/tenants/tenant%20%2F%20one/embedding-configs/connection-test",
    );
  });
});
