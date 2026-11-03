import { endpoints } from "@/shared/api/endpoints";
import { knowledgeAdminApi } from "@/shared/api/knowledgeClient";
import { modelConfigAdminApi } from "@/shared/api/modelConfigClient";
import { withSearchQuery } from "@/shared/api/query";
import { http } from "@/shared/api/transport";
import type {
  AdminAgent,
  AgentAvatarAttach,
  AgentAvatarUploadGrant,
  AgentAvatarUploadRequest,
  AgentCreate,
  AgentLlmBindings,
  AgentLlmBindingsUpdate,
  AgentMcpServerBindings,
  AgentMcpServerBindingsUpdate,
  AgentMcpToolRecall,
  AgentMcpToolRecallRequest,
  AgentSkillBindings,
  AgentSkillBindingsUpdate,
  AgentSkillRecall,
  AgentSkillRecallRequest,
  AgentType,
  AgentUpdate,
  Assignment,
  AuditRecord,
  CurrentUserProfileUpdate,
  ConversationMessage,
  ConversationSummary,
  DashboardOverview,
  Group,
  GroupCreate,
  ImAgentBinding,
  ImChannel,
  ImChannelCreate,
  ImChannelType,
  McpServer,
  McpServerCreate,
  McpDiscoveredTool,
  McpServerUpdate,
  Memory,
  AgentMemorySearchPage,
  MemoryCreate,
  MemoryUpdate,
  Permission,
  Role,
  RoleCreate,
  Run,
  RunDiagnosticTrace,
  RunEvent,
  RunRequester,
  RunTaskBoard,
  Schedule,
  ScheduleCreate,
  ScheduleExecution,
  ScheduleUpdate,
  SessionData,
  Skill,
  SkillBuild,
  SkillCreate,
  SkillDraftDirectoryCreate,
  SkillDraftEntryDelete,
  SkillDraftEntryMutation,
  SkillDraftFileCreate,
  SkillDraftFileWrite,
  SkillFile,
  SkillFileContent,
  SkillUpdate,
  SkillVersion,
  Tenant,
  TenantCreate,
  User,
  UserAvatarAttach,
  UserAvatarUploadGrant,
  UserAvatarUploadRequest,
  UserCreate,
  UserUpdate,
} from "@/shared/api/types";

export { publicApi } from "@/shared/api/publicClient";
export { http } from "@/shared/api/transport";

export const authApi = {
  login: (username: string, password: string) =>
    http.post<SessionData>(endpoints.auth.login, { username, password }),
  session: () => http.get<SessionData>(endpoints.auth.session),
  updateProfile: (payload: CurrentUserProfileUpdate) =>
    http.patch<{ updated: boolean }>(endpoints.auth.profile, payload),
  issueCurrentUserAvatarUploadGrant: (payload: UserAvatarUploadRequest) =>
    http.post<UserAvatarUploadGrant>(endpoints.auth.profileAvatarUploadGrant, payload),
  attachCurrentUserAvatar: (payload: UserAvatarAttach) =>
    http.put<{ attached: boolean }>(endpoints.auth.profileAvatar, payload),
  logout: () => http.post<{ revoked: boolean }>(endpoints.auth.logout, {}),
  switchTenant: (tenantId: string) =>
    http.put<SessionData>(endpoints.auth.switchTenant, { tenant_id: tenantId }),
  changePassword: (currentPassword: string, newPassword: string) =>
    http.post<{ changed: boolean }>(endpoints.auth.password, {
      current_password: currentPassword,
      new_password: newPassword,
    }),
};

export const adminApi = {
  ...knowledgeAdminApi,
  ...modelConfigAdminApi,
  listAgentTypes: () => http.get<AgentType[]>(endpoints.admin.agentTypes),
  dashboard: (tenantId: string) => http.get<DashboardOverview>(endpoints.admin.dashboard(tenantId)),
  listTenants: (query = "") => http.get<Tenant[]>(withSearchQuery(endpoints.admin.tenants, query)),
  createTenant: (payload: TenantCreate) => http.post<Tenant>(endpoints.admin.tenants, payload),
  listUsers: (tenantId: string, query = "") =>
    http.get<User[]>(withSearchQuery(endpoints.admin.users(tenantId), query)),
  createUser: (tenantId: string, payload: UserCreate) =>
    http.post<User>(endpoints.admin.users(tenantId), payload),
  updateUser: (tenantId: string, userId: string, payload: UserUpdate) =>
    http.patch<User>(endpoints.admin.user(tenantId, userId), payload),
  issueUserAvatarUploadGrant: (
    tenantId: string,
    userId: string,
    payload: UserAvatarUploadRequest,
  ) =>
    http.post<UserAvatarUploadGrant>(
      endpoints.admin.userAvatarUploadGrant(tenantId, userId),
      payload,
    ),
  attachUserAvatar: (tenantId: string, userId: string, payload: UserAvatarAttach) =>
    http.put<{ attached: boolean }>(endpoints.admin.userAvatar(tenantId, userId), payload),
  resetUserPassword: (tenantId: string, userId: string, temporaryPassword: string) =>
    http.post<{ reset: boolean }>(endpoints.admin.userPasswordReset(tenantId, userId), {
      temporary_password: temporaryPassword,
    }),
  listGroups: (tenantId: string, query = "") =>
    http.get<Group[]>(withSearchQuery(endpoints.admin.groups(tenantId), query)),
  createGroup: (tenantId: string, payload: GroupCreate) =>
    http.post<Group>(endpoints.admin.groups(tenantId), payload),
  getGroupMembers: (tenantId: string, groupId: string) =>
    http.get<Assignment>(endpoints.admin.groupMembers(tenantId, groupId)),
  replaceGroupMembers: (tenantId: string, groupId: string, ids: string[]) =>
    http.put<{ updated: boolean }>(endpoints.admin.groupMembers(tenantId, groupId), { ids }),
  getGroupRoles: (tenantId: string, groupId: string) =>
    http.get<Assignment>(endpoints.admin.groupRoles(tenantId, groupId)),
  replaceGroupRoles: (tenantId: string, groupId: string, ids: string[]) =>
    http.put<{ updated: boolean }>(endpoints.admin.groupRoles(tenantId, groupId), { ids }),
  listRoles: (tenantId: string, query = "") =>
    http.get<Role[]>(withSearchQuery(endpoints.admin.roles(tenantId), query)),
  createRole: (tenantId: string, payload: RoleCreate) =>
    http.post<Role>(endpoints.admin.roles(tenantId), payload),
  getUserRoles: (tenantId: string, userId: string) =>
    http.get<Assignment>(endpoints.admin.userRoles(tenantId, userId)),
  replaceUserRoles: (tenantId: string, userId: string, ids: string[]) =>
    http.put<{ updated: boolean }>(endpoints.admin.userRoles(tenantId, userId), { ids }),
  listPermissions: () => http.get<Permission[]>(endpoints.admin.permissions),
  listAgents: (tenantId: string, query = "") =>
    http.get<AdminAgent[]>(withSearchQuery(endpoints.admin.agents(tenantId), query)),
  createAgent: (tenantId: string, payload: AgentCreate) =>
    http.post<AdminAgent>(endpoints.admin.agents(tenantId), payload),
  updateAgent: (tenantId: string, agentId: string, payload: AgentUpdate) =>
    http.patch<AdminAgent>(endpoints.admin.agent(tenantId, agentId), payload),
  listImChannels: (tenantId: string) => http.get<ImChannel[]>(endpoints.admin.imChannels(tenantId)),
  listImChannelTypes: (tenantId: string) =>
    http.get<ImChannelType[]>(endpoints.admin.imChannelTypes(tenantId)),
  createImChannel: (tenantId: string, payload: ImChannelCreate) =>
    http.post<ImChannel>(endpoints.admin.imChannels(tenantId), payload),
  listAgentImBindings: (tenantId: string, agentId: string) =>
    http.get<ImAgentBinding[]>(endpoints.admin.agentImBindings(tenantId, agentId)),
  bindImChannel: (tenantId: string, channelId: string, agentId: string) =>
    http.put<ImAgentBinding>(endpoints.admin.imAgentBindings(tenantId), {
      channel_id: channelId,
      agent_id: agentId,
    }),
  issueAgentAvatarUploadGrant: (
    tenantId: string,
    agentId: string,
    payload: AgentAvatarUploadRequest,
  ) =>
    http.post<AgentAvatarUploadGrant>(
      endpoints.admin.agentAvatarUploadGrant(tenantId, agentId),
      payload,
    ),
  attachAgentAvatar: (tenantId: string, agentId: string, payload: AgentAvatarAttach) =>
    http.put<AdminAgent>(endpoints.admin.agentAvatar(tenantId, agentId), payload),
  getAgentLlmBindings: (tenantId: string, agentId: string) =>
    http.get<AgentLlmBindings>(endpoints.admin.agentLlmConfigs(tenantId, agentId)),
  replaceAgentLlmBindings: (tenantId: string, agentId: string, payload: AgentLlmBindingsUpdate) =>
    http.put<AgentLlmBindings>(endpoints.admin.agentLlmConfigs(tenantId, agentId), payload),
  getAgentSkillBindings: (tenantId: string, agentId: string) =>
    http.get<AgentSkillBindings>(endpoints.admin.agentSkills(tenantId, agentId)),
  replaceAgentSkillBindings: (
    tenantId: string,
    agentId: string,
    payload: AgentSkillBindingsUpdate,
  ) => http.put<AgentSkillBindings>(endpoints.admin.agentSkills(tenantId, agentId), payload),
  searchAgentSkills: (tenantId: string, agentId: string, payload: AgentSkillRecallRequest) =>
    http.post<AgentSkillRecall>(endpoints.admin.agentSkillRecall(tenantId, agentId), payload),
  searchAgentMcpTools: (tenantId: string, agentId: string, payload: AgentMcpToolRecallRequest) =>
    http.post<AgentMcpToolRecall>(endpoints.admin.agentMcpToolRecall(tenantId, agentId), payload),
  getAgentMcpServerBindings: (tenantId: string, agentId: string) =>
    http.get<AgentMcpServerBindings>(endpoints.admin.agentMcpServers(tenantId, agentId)),
  replaceAgentMcpServerBindings: (
    tenantId: string,
    agentId: string,
    payload: AgentMcpServerBindingsUpdate,
  ) =>
    http.put<AgentMcpServerBindings>(endpoints.admin.agentMcpServers(tenantId, agentId), payload),
  listSkills: (tenantId: string, query = "") =>
    http.get<Skill[]>(withSearchQuery(endpoints.admin.skills(tenantId), query)),
  createSkill: (tenantId: string, payload: SkillCreate) =>
    http.post<Skill>(endpoints.admin.skills(tenantId), payload),
  importSkill: (tenantId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return http.postForm<Skill>(endpoints.admin.skillImport(tenantId), form);
  },
  updateSkill: (tenantId: string, skillId: string, payload: SkillUpdate) =>
    http.patch<Skill>(endpoints.admin.skill(tenantId, skillId), payload),
  deleteSkill: (tenantId: string, skillId: string) =>
    http.delete<{ deleted: boolean }>(endpoints.admin.skill(tenantId, skillId), {}),
  listSkillVersions: (tenantId: string, skillId: string) =>
    http.get<SkillVersion[]>(endpoints.admin.skillVersions(tenantId, skillId)),
  forkSkillDraft: (tenantId: string, skillId: string, sourceVersionId?: string) =>
    http.post<SkillVersion>(endpoints.admin.skillDraftFork(tenantId, skillId), {
      source_version_id: sourceVersionId ?? null,
    }),
  buildSkillDraft: (tenantId: string, skillId: string) =>
    http.post<SkillBuild>(endpoints.admin.skillDraftBuild(tenantId, skillId), {}),
  getSkillDraftBuild: (tenantId: string, skillId: string) =>
    http.get<SkillBuild | null>(endpoints.admin.skillDraftBuildStatus(tenantId, skillId)),
  publishSkill: (tenantId: string, skillId: string) =>
    http.post<Skill>(endpoints.admin.skillPublish(tenantId, skillId), {}),
  rollbackSkill: (tenantId: string, skillId: string, versionId: string) =>
    http.post<Skill>(endpoints.admin.skillRollback(tenantId, skillId), { version_id: versionId }),
  listSkillVersionFiles: (tenantId: string, skillId: string, versionId: string) =>
    http.get<SkillFile[]>(endpoints.admin.skillVersionFiles(tenantId, skillId, versionId)),
  getSkillVersionFile: (tenantId: string, skillId: string, versionId: string, path: string) =>
    http.get<SkillFileContent>(
      `${endpoints.admin.skillVersionFileContent(tenantId, skillId, versionId)}?${new URLSearchParams({ path })}`,
    ),
  writeSkillDraftFile: (
    tenantId: string,
    skillId: string,
    path: string,
    payload: SkillDraftFileWrite,
  ) =>
    http.put<SkillFileContent>(
      `${endpoints.admin.skillDraftFileContent(tenantId, skillId)}?${new URLSearchParams({ path })}`,
      payload,
    ),
  createSkillDraftFile: (tenantId: string, skillId: string, payload: SkillDraftFileCreate) =>
    http.post<SkillDraftEntryMutation>(endpoints.admin.skillDraftFiles(tenantId, skillId), payload),
  createSkillDraftDirectory: (
    tenantId: string,
    skillId: string,
    payload: SkillDraftDirectoryCreate,
  ) =>
    http.post<SkillDraftEntryMutation>(
      endpoints.admin.skillDraftDirectories(tenantId, skillId),
      payload,
    ),
  deleteSkillDraftEntry: (tenantId: string, skillId: string, payload: SkillDraftEntryDelete) =>
    http.delete<SkillDraftEntryMutation>(
      endpoints.admin.skillDraftEntries(tenantId, skillId),
      payload,
    ),
  listMcpServers: (tenantId: string, query = "") =>
    http.get<McpServer[]>(withSearchQuery(endpoints.admin.mcpServers(tenantId), query)),
  createMcpServer: (tenantId: string, payload: McpServerCreate) =>
    http.post<McpServer>(endpoints.admin.mcpServers(tenantId), payload),
  updateMcpServer: (tenantId: string, serverId: string, payload: McpServerUpdate) =>
    http.patch<McpServer>(endpoints.admin.mcpServer(tenantId, serverId), payload),
  discoverMcpTools: (tenantId: string, serverId: string) =>
    http.post<McpDiscoveredTool[]>(endpoints.admin.mcpServerDiscoverTools(tenantId, serverId), {}),
  listRuns: (
    tenantId: string,
    {
      actorId,
      actorType,
      limit = 100,
      status = "",
    }: { actorId?: string; actorType?: string; limit?: number; status?: string } = {},
  ) => {
    const query = new URLSearchParams();
    if (status) query.set("status", status);
    if (actorType && actorId) {
      query.set("actor_type", actorType);
      query.set("actor_id", actorId);
    }
    query.set("limit", String(limit));
    const suffix = query.size ? `?${query.toString()}` : "";
    return http.get<Run[]>(`${endpoints.admin.runs(tenantId)}${suffix}`);
  },
  listRunRequesters: (
    tenantId: string,
    { actorType = "", query = "" }: { actorType?: string; query?: string } = {},
  ) => {
    const params = new URLSearchParams({ limit: "100" });
    if (actorType) params.set("actor_type", actorType);
    if (query.trim()) params.set("query", query.trim());
    return http.get<RunRequester[]>(`${endpoints.admin.runRequesters(tenantId)}?${params}`);
  },
  listRunConversations: (
    tenantId: string,
    { actorId, actorType, limit = 100 }: { actorId: string; actorType: string; limit?: number },
  ) => {
    const params = new URLSearchParams({
      actor_id: actorId,
      actor_type: actorType,
      limit: String(limit),
    });
    return http.get<ConversationSummary[]>(
      `${endpoints.admin.runConversations(tenantId)}?${params}`,
    );
  },
  listRunConversationMessages: (
    tenantId: string,
    {
      actorId,
      actorType,
      conversationId,
    }: {
      actorId: string;
      actorType: string;
      conversationId: string;
    },
  ) => {
    const params = new URLSearchParams({ actor_id: actorId, actor_type: actorType });
    return http.get<ConversationMessage[]>(
      `${endpoints.admin.runConversationMessages(tenantId, conversationId)}?${params}`,
    );
  },
  getRun: (tenantId: string, runId: string) => http.get<Run>(endpoints.admin.run(tenantId, runId)),
  listRunDiagnosticTraces: (tenantId: string, runId: string) =>
    http.get<RunDiagnosticTrace[]>(endpoints.admin.runDiagnosticTraces(tenantId, runId)),
  listRunEvents: (tenantId: string, runId: string) =>
    http.get<RunEvent[]>(endpoints.admin.runEvents(tenantId, runId)),
  getRunTaskBoard: (tenantId: string, runId: string) =>
    http.get<RunTaskBoard>(endpoints.admin.runTaskBoard(tenantId, runId)),
  listMemory: (tenantId: string, query = "", status = "") => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("query", query.trim());
    if (status) params.set("status", status);
    const suffix = params.size ? `?${params}` : "";
    return http.get<Memory[]>(`${endpoints.admin.memory(tenantId)}${suffix}`);
  },
  searchAgentMemory: (
    tenantId: string,
    {
      agentId,
      actorId,
      query = "",
      offset = 0,
      limit = 20,
    }: {
      agentId: string;
      actorId?: string;
      query?: string;
      offset?: number;
      limit?: number;
    },
  ) => {
    const params = new URLSearchParams({
      agent_id: agentId,
      offset: String(offset),
      limit: String(limit),
    });
    if (actorId) params.set("actor_id", actorId);
    if (query.trim()) params.set("query", query.trim());
    return http.get<AgentMemorySearchPage>(
      `${endpoints.admin.memoryAgentView(tenantId)}?${params}`,
    );
  },
  createMemory: (tenantId: string, payload: MemoryCreate) =>
    http.post<Memory>(endpoints.admin.memory(tenantId), payload),
  updateMemory: (tenantId: string, memoryId: string, payload: MemoryUpdate) =>
    http.put<Memory>(endpoints.admin.memoryItem(tenantId, memoryId), payload),
  archiveMemory: (tenantId: string, memoryId: string, expectedVersion: number) =>
    http.post<Memory>(endpoints.admin.memoryArchive(tenantId, memoryId), {
      expected_version: expectedVersion,
    }),
  listSchedules: (tenantId: string, query = "") =>
    http.get<Schedule[]>(withSearchQuery(endpoints.admin.schedules(tenantId), query)),
  createSchedule: (tenantId: string, payload: ScheduleCreate) =>
    http.post<Schedule>(endpoints.admin.schedules(tenantId), payload),
  updateSchedule: (tenantId: string, scheduleId: string, payload: ScheduleUpdate) =>
    http.put<Schedule>(endpoints.admin.schedule(tenantId, scheduleId), payload),
  setScheduleEnabled: (tenantId: string, scheduleId: string, enabled: boolean) =>
    http.post<Schedule>(
      endpoints.admin.scheduleAction(tenantId, scheduleId, enabled ? "enable" : "disable"),
      {},
    ),
  runScheduleNow: (tenantId: string, scheduleId: string) =>
    http.post<ScheduleExecution>(
      endpoints.admin.scheduleAction(tenantId, scheduleId, "run-now"),
      {},
    ),
  listScheduleExecutions: (tenantId: string, scheduleId: string) =>
    http.get<ScheduleExecution[]>(endpoints.admin.scheduleExecutions(tenantId, scheduleId)),
  listAudit: (tenantId: string, query = "") =>
    http.get<AuditRecord[]>(withSearchQuery(endpoints.admin.audit(tenantId), query)),
};
