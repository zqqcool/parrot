import type { paths } from "@/shared/api/generated/schema";

type ApiPath = Extract<keyof paths, string>;
type ScheduleAction = "disable" | "enable" | "run-now";

function staticPath<Path extends ApiPath>(path: Path): Path {
  return path;
}

function dynamicPath<Path extends ApiPath>(path: Path, params: Record<string, string>): string {
  let resolved: string = path;
  for (const [name, value] of Object.entries(params)) {
    resolved = resolved.replace(`{${name}}`, encodeURIComponent(value));
  }
  return resolved;
}

function scheduleActionPath(tenantId: string, scheduleId: string, action: ScheduleAction): string {
  const params = { tenant_id: tenantId, schedule_id: scheduleId };
  if (action === "disable") {
    return dynamicPath("/api/v1/admin/tenants/{tenant_id}/schedules/{schedule_id}/disable", params);
  }
  if (action === "enable") {
    return dynamicPath("/api/v1/admin/tenants/{tenant_id}/schedules/{schedule_id}/enable", params);
  }
  return dynamicPath("/api/v1/admin/tenants/{tenant_id}/schedules/{schedule_id}/run-now", params);
}

export const endpoints = {
  auth: {
    login: staticPath("/api/v1/auth/login"),
    session: staticPath("/api/v1/auth/session"),
    profile: staticPath("/api/v1/auth/profile"),
    profileAvatar: staticPath("/api/v1/auth/profile/avatar"),
    profileAvatarUploadGrant: staticPath("/api/v1/auth/profile/avatar-upload-grant"),
    logout: staticPath("/api/v1/auth/logout"),
    password: staticPath("/api/v1/auth/password"),
    switchTenant: staticPath("/api/v1/auth/session/tenant"),
  },
  public: {
    agents: staticPath("/api/v1/public/agents"),
    agent: (slug: string) => dynamicPath("/api/v1/public/agents/{slug}", { slug }),
    agentChannels: (slug: string) => dynamicPath("/api/v1/public/agents/{slug}/channels", { slug }),
    agentAvatar: (slug: string) => dynamicPath("/api/v1/public/agents/{slug}/avatar", { slug }),
  },
  im: {
    knowledgeMediaContent: (interactionId: string, assetId: string) =>
      `/api/v1/im/interactions/${encodeURIComponent(interactionId)}/knowledge/media/${encodeURIComponent(assetId)}/content`,
  },
  admin: {
    agentTypes: staticPath("/api/v1/admin/agent-types"),
    dashboard: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/dashboard", { tenant_id: tenantId }),
    tenants: staticPath("/api/v1/admin/tenants"),
    users: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/users", { tenant_id: tenantId }),
    user: (tenantId: string, userId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/users/{user_id}", {
        tenant_id: tenantId,
        user_id: userId,
      }),
    userPasswordReset: (tenantId: string, userId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/users/{user_id}/password-reset", {
        tenant_id: tenantId,
        user_id: userId,
      }),
    groups: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/groups", { tenant_id: tenantId }),
    groupMembers: (tenantId: string, groupId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/groups/{group_id}/members", {
        tenant_id: tenantId,
        group_id: groupId,
      }),
    groupRoles: (tenantId: string, groupId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/groups/{group_id}/roles", {
        tenant_id: tenantId,
        group_id: groupId,
      }),
    roles: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/roles", { tenant_id: tenantId }),
    userRoles: (tenantId: string, userId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/users/{user_id}/roles", {
        tenant_id: tenantId,
        user_id: userId,
      }),
    userAvatar: (tenantId: string, userId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/users/{user_id}/avatar", {
        tenant_id: tenantId,
        user_id: userId,
      }),
    userAvatarUploadGrant: (tenantId: string, userId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/users/{user_id}/avatar-upload-grant", {
        tenant_id: tenantId,
        user_id: userId,
      }),
    agents: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/agents", { tenant_id: tenantId }),
    agent: (tenantId: string, agentId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}", {
        tenant_id: tenantId,
        agent_id: agentId,
      }),
    agentImBindings: (tenantId: string, agentId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/im-bindings", {
        tenant_id: tenantId,
        agent_id: agentId,
      }),
    imChannels: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/im/channels", { tenant_id: tenantId }),
    imChannelTypes: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/im/channel-types", { tenant_id: tenantId }),
    imAgentBindings: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/im/agent-bindings", {
        tenant_id: tenantId,
      }),
    agentAvatar: (tenantId: string, agentId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/avatar", {
        tenant_id: tenantId,
        agent_id: agentId,
      }),
    agentAvatarUploadGrant: (tenantId: string, agentId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/avatar-upload-grant", {
        tenant_id: tenantId,
        agent_id: agentId,
      }),
    agentLlmConfigs: (tenantId: string, agentId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/llm-configs", {
        tenant_id: tenantId,
        agent_id: agentId,
      }),
    agentSkills: (tenantId: string, agentId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/skills", {
        tenant_id: tenantId,
        agent_id: agentId,
      }),
    agentSkillRecall: (tenantId: string, agentId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/skills:search", {
        tenant_id: tenantId,
        agent_id: agentId,
      }),
    agentMcpToolRecall: (tenantId: string, agentId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/mcp-tools:search", {
        tenant_id: tenantId,
        agent_id: agentId,
      }),
    agentMcpServers: (tenantId: string, agentId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/mcp-servers", {
        tenant_id: tenantId,
        agent_id: agentId,
      }),
    agentKnowledgeSpaces: (tenantId: string, agentId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/knowledge-spaces", {
        tenant_id: tenantId,
        agent_id: agentId,
      }),
    agentKnowledgeSpace: (tenantId: string, agentId: string, spaceId: string) =>
      dynamicPath(
        "/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/knowledge-spaces/{space_id}",
        {
          tenant_id: tenantId,
          agent_id: agentId,
          space_id: spaceId,
        },
      ),
    agentKnowledgeSearchTest: (tenantId: string, agentId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/agents/{agent_id}/knowledge-search-test", {
        tenant_id: tenantId,
        agent_id: agentId,
      }),
    knowledgeSpaces: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/spaces", {
        tenant_id: tenantId,
      }),
    knowledgeMergeSettings: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/merge-settings", {
        tenant_id: tenantId,
      }),
    knowledgeSpace: (tenantId: string, spaceId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/spaces/{space_id}", {
        tenant_id: tenantId,
        space_id: spaceId,
      }),
    knowledgeSpaceChunking: (tenantId: string, spaceId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/spaces/{space_id}/chunking", {
        tenant_id: tenantId,
        space_id: spaceId,
      }),
    knowledgeSpaceRetrieval: (tenantId: string, spaceId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/spaces/{space_id}/retrieval", {
        tenant_id: tenantId,
        space_id: spaceId,
      }),
    knowledgeSpaceAgents: (tenantId: string, spaceId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/spaces/{space_id}/agents", {
        tenant_id: tenantId,
        space_id: spaceId,
      }),
    knowledgeDocuments: (tenantId: string, spaceId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/spaces/{space_id}/documents", {
        tenant_id: tenantId,
        space_id: spaceId,
      }),
    knowledgeSources: (tenantId: string, spaceId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/spaces/{space_id}/sources", {
        tenant_id: tenantId,
        space_id: spaceId,
      }),
    knowledgeSearch: (tenantId: string, spaceId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/spaces/{space_id}/search", {
        tenant_id: tenantId,
        space_id: spaceId,
      }),
    knowledgeCitation: (tenantId: string, citationId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/citations/{citation_id}", {
        tenant_id: tenantId,
        citation_id: citationId,
      }),
    knowledgeMediaContent: (tenantId: string, assetId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/media/{asset_id}/content", {
        tenant_id: tenantId,
        asset_id: assetId,
      }),
    knowledgeActiveIngestions: (tenantId: string, spaceId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/spaces/{space_id}/ingestions", {
        tenant_id: tenantId,
        space_id: spaceId,
      }),
    knowledgeDocumentUploadGrant: (tenantId: string, spaceId: string) =>
      dynamicPath(
        "/api/v1/admin/tenants/{tenant_id}/knowledge/spaces/{space_id}/document-upload-grants",
        { tenant_id: tenantId, space_id: spaceId },
      ),
    knowledgeDocumentVersionUploadGrant: (tenantId: string, documentId: string) =>
      dynamicPath(
        "/api/v1/admin/tenants/{tenant_id}/knowledge/documents/{document_id}/version-upload-grants",
        { tenant_id: tenantId, document_id: documentId },
      ),
    knowledgeDocumentTextVersion: (tenantId: string, documentId: string) =>
      dynamicPath(
        "/api/v1/admin/tenants/{tenant_id}/knowledge/documents/{document_id}/text-versions",
        { tenant_id: tenantId, document_id: documentId },
      ),
    knowledgeDocumentVersions: (tenantId: string, documentId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/documents/{document_id}/versions", {
        tenant_id: tenantId,
        document_id: documentId,
      }),
    knowledgeDocumentVersionChunks: (tenantId: string, documentId: string, versionId: string) =>
      dynamicPath(
        "/api/v1/admin/tenants/{tenant_id}/knowledge/documents/{document_id}/versions/{version_id}/chunks",
        { tenant_id: tenantId, document_id: documentId, version_id: versionId },
      ),
    knowledgeDocumentVersionSource: (tenantId: string, documentId: string, versionId: string) =>
      dynamicPath(
        "/api/v1/admin/tenants/{tenant_id}/knowledge/documents/{document_id}/versions/{version_id}/source",
        { tenant_id: tenantId, document_id: documentId, version_id: versionId },
      ),
    knowledgeSourceConfirm: (tenantId: string, sourceId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/sources/{source_id}/confirm", {
        tenant_id: tenantId,
        source_id: sourceId,
      }),
    knowledgeSourceRetryConfirm: (tenantId: string, sourceId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/sources/{source_id}/retry-confirm", {
        tenant_id: tenantId,
        source_id: sourceId,
      }),
    knowledgeSourceCleanup: (tenantId: string, sourceId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/sources/{source_id}", {
        tenant_id: tenantId,
        source_id: sourceId,
      }),
    knowledgeIngestion: (tenantId: string, jobId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/ingestions/{job_id}", {
        tenant_id: tenantId,
        job_id: jobId,
      }),
    knowledgeDocumentArchive: (tenantId: string, documentId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/knowledge/documents/{document_id}/archive", {
        tenant_id: tenantId,
        document_id: documentId,
      }),
    llmConfigs: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/llm-configs", { tenant_id: tenantId }),
    embeddingConfigs: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/embedding-configs", { tenant_id: tenantId }),
    rerankerConfigs: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/reranker-configs", { tenant_id: tenantId }),
    modelProviders: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/model-providers", { tenant_id: tenantId }),
    skills: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/skills", { tenant_id: tenantId }),
    skillImport: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/skills/import", { tenant_id: tenantId }),
    skill: (tenantId: string, skillId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}", {
        tenant_id: tenantId,
        skill_id: skillId,
      }),
    skillVersions: (tenantId: string, skillId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}/versions", {
        tenant_id: tenantId,
        skill_id: skillId,
      }),
    skillDraftFork: (tenantId: string, skillId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}/draft:fork", {
        tenant_id: tenantId,
        skill_id: skillId,
      }),
    skillDraftBuild: (tenantId: string, skillId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}/draft:build", {
        tenant_id: tenantId,
        skill_id: skillId,
      }),
    skillDraftBuildStatus: (tenantId: string, skillId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}/draft/build", {
        tenant_id: tenantId,
        skill_id: skillId,
      }),
    skillPublish: (tenantId: string, skillId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}:publish", {
        tenant_id: tenantId,
        skill_id: skillId,
      }),
    skillRollback: (tenantId: string, skillId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}:rollback", {
        tenant_id: tenantId,
        skill_id: skillId,
      }),
    skillVersionFiles: (tenantId: string, skillId: string, versionId: string) =>
      dynamicPath(
        "/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}/versions/{version_id}/files",
        { tenant_id: tenantId, skill_id: skillId, version_id: versionId },
      ),
    skillVersionFileContent: (tenantId: string, skillId: string, versionId: string) =>
      dynamicPath(
        "/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}/versions/{version_id}/files/content",
        { tenant_id: tenantId, skill_id: skillId, version_id: versionId },
      ),
    skillDraftFileContent: (tenantId: string, skillId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}/draft/files/content", {
        tenant_id: tenantId,
        skill_id: skillId,
      }),
    skillDraftFiles: (tenantId: string, skillId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}/draft/files", {
        tenant_id: tenantId,
        skill_id: skillId,
      }),
    skillDraftDirectories: (tenantId: string, skillId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}/draft/directories", {
        tenant_id: tenantId,
        skill_id: skillId,
      }),
    skillDraftEntries: (tenantId: string, skillId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/skills/{skill_id}/draft/entries", {
        tenant_id: tenantId,
        skill_id: skillId,
      }),
    mcpServers: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/mcp-servers", { tenant_id: tenantId }),
    mcpServer: (tenantId: string, serverId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/mcp-servers/{server_id}", {
        tenant_id: tenantId,
        server_id: serverId,
      }),
    mcpServerDiscoverTools: (tenantId: string, serverId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/mcp-servers/{server_id}/discover-tools", {
        tenant_id: tenantId,
        server_id: serverId,
      }),
    llmConfig: (tenantId: string, configId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/llm-configs/{config_id}", {
        tenant_id: tenantId,
        config_id: configId,
      }),
    llmConfigConnectionTest: (tenantId: string, configId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/llm-configs/{config_id}/connection-test", {
        tenant_id: tenantId,
        config_id: configId,
      }),
    llmConfigDraftConnectionTest: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/llm-configs/connection-test", {
        tenant_id: tenantId,
      }),
    embeddingConfig: (tenantId: string, configId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/embedding-configs/{config_id}", {
        tenant_id: tenantId,
        config_id: configId,
      }),
    embeddingConfigConnectionTest: (tenantId: string, configId: string) =>
      dynamicPath(
        "/api/v1/admin/tenants/{tenant_id}/embedding-configs/{config_id}/connection-test",
        { tenant_id: tenantId, config_id: configId },
      ),
    embeddingConfigDraftConnectionTest: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/embedding-configs/connection-test", {
        tenant_id: tenantId,
      }),
    rerankerConfig: (tenantId: string, configId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/reranker-configs/{config_id}", {
        tenant_id: tenantId,
        config_id: configId,
      }),
    rerankerConfigConnectionTest: (tenantId: string, configId: string) =>
      dynamicPath(
        "/api/v1/admin/tenants/{tenant_id}/reranker-configs/{config_id}/connection-test",
        { tenant_id: tenantId, config_id: configId },
      ),
    rerankerConfigDraftConnectionTest: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/reranker-configs/connection-test", {
        tenant_id: tenantId,
      }),
    runs: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/runs", { tenant_id: tenantId }),
    runRequesters: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/runs/requesters", { tenant_id: tenantId }),
    runConversations: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/runs/conversations", {
        tenant_id: tenantId,
      }),
    runConversationMessages: (tenantId: string, conversationId: string) =>
      dynamicPath(
        "/api/v1/admin/tenants/{tenant_id}/runs/conversations/{conversation_id}/messages",
        { tenant_id: tenantId, conversation_id: conversationId },
      ),
    run: (tenantId: string, runId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/runs/{run_id}", {
        tenant_id: tenantId,
        run_id: runId,
      }),
    runEvents: (tenantId: string, runId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/runs/{run_id}/events", {
        tenant_id: tenantId,
        run_id: runId,
      }),
    runDiagnosticTraces: (tenantId: string, runId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/runs/{run_id}/diagnostic-traces", {
        tenant_id: tenantId,
        run_id: runId,
      }),
    runTaskBoard: (tenantId: string, runId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/runs/{run_id}/task-board", {
        tenant_id: tenantId,
        run_id: runId,
      }),
    memory: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/memory", { tenant_id: tenantId }),
    memoryAgentView: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/memory/agent-view", {
        tenant_id: tenantId,
      }),
    memoryItem: (tenantId: string, memoryId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/memory/{memory_id}", {
        tenant_id: tenantId,
        memory_id: memoryId,
      }),
    memoryArchive: (tenantId: string, memoryId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/memory/{memory_id}/archive", {
        tenant_id: tenantId,
        memory_id: memoryId,
      }),
    schedules: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/schedules", { tenant_id: tenantId }),
    schedule: (tenantId: string, scheduleId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/schedules/{schedule_id}", {
        tenant_id: tenantId,
        schedule_id: scheduleId,
      }),
    scheduleAction: scheduleActionPath,
    scheduleExecutions: (tenantId: string, scheduleId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/schedules/{schedule_id}/executions", {
        tenant_id: tenantId,
        schedule_id: scheduleId,
      }),
    audit: (tenantId: string) =>
      dynamicPath("/api/v1/admin/tenants/{tenant_id}/audit-logs", { tenant_id: tenantId }),
    permissions: staticPath("/api/v1/admin/permissions"),
  },
} as const;
