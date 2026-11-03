import { endpoints } from "@/shared/api/endpoints";
import { withSearchQuery } from "@/shared/api/query";
import { http } from "@/shared/api/transport";
import type {
  AgentKnowledgeSearchTest,
  AgentKnowledgeSearchTestRequest,
  AgentKnowledgeSpaceBindings,
  AgentKnowledgeSpaceBindingsUpdate,
  KnowledgeCitation,
  KnowledgeDocument,
  KnowledgeDocumentChunkPage,
  KnowledgeDocumentCreate,
  KnowledgeDocumentTextVersionCreate,
  KnowledgeDocumentVersion,
  KnowledgeDocumentVersionUpload,
  KnowledgeIngestion,
  KnowledgeMergeSettings,
  KnowledgeMergeSettingsUpdate,
  KnowledgeSearchResult,
  KnowledgeSourceActivityPage,
  KnowledgeSourceConfirm,
  KnowledgeSourceUpload,
  KnowledgeSourceUploadGrant,
  KnowledgeSpace,
  KnowledgeSpaceAgentBindings,
  KnowledgeSpaceChunkingUpdate,
  KnowledgeSpaceCreate,
  KnowledgeSpaceRetrievalUpdate,
} from "@/shared/api/types";

export const knowledgeAdminApi = {
  listKnowledgeSpaces: (tenantId: string, query = "") =>
    http.get<KnowledgeSpace[]>(withSearchQuery(endpoints.admin.knowledgeSpaces(tenantId), query)),
  getKnowledgeMergeSettings: (tenantId: string) =>
    http.get<KnowledgeMergeSettings>(endpoints.admin.knowledgeMergeSettings(tenantId)),
  updateKnowledgeMergeSettings: (tenantId: string, payload: KnowledgeMergeSettingsUpdate) =>
    http.put<KnowledgeMergeSettings>(endpoints.admin.knowledgeMergeSettings(tenantId), payload),
  createKnowledgeSpace: (tenantId: string, payload: KnowledgeSpaceCreate) =>
    http.post<KnowledgeSpace>(endpoints.admin.knowledgeSpaces(tenantId), payload),
  deleteKnowledgeSpace: (tenantId: string, spaceId: string) =>
    http.delete<null>(endpoints.admin.knowledgeSpace(tenantId, spaceId), {}),
  updateKnowledgeSpaceChunking: (
    tenantId: string,
    spaceId: string,
    payload: KnowledgeSpaceChunkingUpdate,
  ) =>
    http.patch<KnowledgeSpace>(endpoints.admin.knowledgeSpaceChunking(tenantId, spaceId), payload),
  updateKnowledgeSpaceRetrieval: (
    tenantId: string,
    spaceId: string,
    payload: KnowledgeSpaceRetrievalUpdate,
  ) =>
    http.patch<KnowledgeSpace>(endpoints.admin.knowledgeSpaceRetrieval(tenantId, spaceId), payload),
  getKnowledgeSpaceAgents: (tenantId: string, spaceId: string) =>
    http.get<KnowledgeSpaceAgentBindings>(endpoints.admin.knowledgeSpaceAgents(tenantId, spaceId)),
  listKnowledgeDocuments: (tenantId: string, spaceId: string, query = "") =>
    http.get<KnowledgeDocument[]>(
      withSearchQuery(endpoints.admin.knowledgeDocuments(tenantId, spaceId), query),
    ),
  listKnowledgeSources: (tenantId: string, spaceId: string, page: number, pageSize: number) =>
    http.get<KnowledgeSourceActivityPage>(
      `${endpoints.admin.knowledgeSources(tenantId, spaceId)}?${new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      })}`,
    ),
  searchKnowledgeSpace: (tenantId: string, spaceId: string, query: string) =>
    http.get<KnowledgeSearchResult[]>(
      `${endpoints.admin.knowledgeSearch(tenantId, spaceId)}?${new URLSearchParams({ query })}`,
    ),
  expandKnowledgeCitation: (tenantId: string, citationId: string) =>
    http.get<KnowledgeCitation>(endpoints.admin.knowledgeCitation(tenantId, citationId)),
  downloadKnowledgeMedia: (tenantId: string, assetId: string) =>
    http.getFile(endpoints.admin.knowledgeMediaContent(tenantId, assetId)),
  listActiveKnowledgeIngestions: (tenantId: string, spaceId: string) =>
    http.get<KnowledgeIngestion[]>(endpoints.admin.knowledgeActiveIngestions(tenantId, spaceId)),
  createKnowledgeDocument: (tenantId: string, spaceId: string, payload: KnowledgeDocumentCreate) =>
    http.post<KnowledgeDocument>(endpoints.admin.knowledgeDocuments(tenantId, spaceId), payload),
  createKnowledgeDocumentTextVersion: (
    tenantId: string,
    documentId: string,
    payload: KnowledgeDocumentTextVersionCreate,
  ) =>
    http.post<KnowledgeDocument>(
      endpoints.admin.knowledgeDocumentTextVersion(tenantId, documentId),
      payload,
    ),
  issueKnowledgeDocumentUpload: (
    tenantId: string,
    spaceId: string,
    payload: KnowledgeSourceUpload,
  ) =>
    http.post<KnowledgeSourceUploadGrant>(
      endpoints.admin.knowledgeDocumentUploadGrant(tenantId, spaceId),
      payload,
    ),
  issueKnowledgeDocumentVersionUpload: (
    tenantId: string,
    documentId: string,
    payload: KnowledgeDocumentVersionUpload,
  ) =>
    http.post<KnowledgeSourceUploadGrant>(
      endpoints.admin.knowledgeDocumentVersionUploadGrant(tenantId, documentId),
      payload,
    ),
  confirmKnowledgeDocumentUpload: (
    tenantId: string,
    sourceId: string,
    payload: KnowledgeSourceConfirm,
  ) =>
    http.post<KnowledgeIngestion>(
      endpoints.admin.knowledgeSourceConfirm(tenantId, sourceId),
      payload,
      {
        idempotencyKey: `knowledge-confirm:${sourceId}`,
        timeoutMs: 75_000,
      },
    ),
  retryKnowledgeDocumentUploadConfirmation: (tenantId: string, sourceId: string) =>
    http.post<KnowledgeIngestion>(
      endpoints.admin.knowledgeSourceRetryConfirm(tenantId, sourceId),
      {},
      {
        idempotencyKey: `knowledge-retry-confirm:${sourceId}`,
        timeoutMs: 75_000,
      },
    ),
  cleanupKnowledgeDocumentUpload: (tenantId: string, sourceId: string) =>
    http.delete<null>(endpoints.admin.knowledgeSourceCleanup(tenantId, sourceId), {}),
  getKnowledgeIngestion: (tenantId: string, jobId: string) =>
    http.get<KnowledgeIngestion>(endpoints.admin.knowledgeIngestion(tenantId, jobId)),
  listKnowledgeDocumentVersions: (tenantId: string, documentId: string) =>
    http.get<KnowledgeDocumentVersion[]>(
      endpoints.admin.knowledgeDocumentVersions(tenantId, documentId),
    ),
  listKnowledgeDocumentVersionChunks: (
    tenantId: string,
    documentId: string,
    versionId: string,
    page: number,
    pageSize: number,
  ) =>
    http.get<KnowledgeDocumentChunkPage>(
      `${endpoints.admin.knowledgeDocumentVersionChunks(tenantId, documentId, versionId)}?${new URLSearchParams({ page: String(page), page_size: String(pageSize) })}`,
    ),
  downloadKnowledgeDocumentVersion: (tenantId: string, documentId: string, versionId: string) =>
    http.getFile(endpoints.admin.knowledgeDocumentVersionSource(tenantId, documentId, versionId)),
  archiveKnowledgeDocument: (tenantId: string, documentId: string) =>
    http.post<null>(endpoints.admin.knowledgeDocumentArchive(tenantId, documentId), {}),
  getAgentKnowledgeSpaces: (tenantId: string, agentId: string) =>
    http.get<AgentKnowledgeSpaceBindings>(endpoints.admin.agentKnowledgeSpaces(tenantId, agentId)),
  replaceAgentKnowledgeSpaces: (
    tenantId: string,
    agentId: string,
    payload: AgentKnowledgeSpaceBindingsUpdate,
  ) =>
    http.put<AgentKnowledgeSpaceBindings>(
      endpoints.admin.agentKnowledgeSpaces(tenantId, agentId),
      payload,
    ),
  addAgentKnowledgeSpace: (tenantId: string, agentId: string, spaceId: string) =>
    http.post<AgentKnowledgeSpaceBindings>(
      endpoints.admin.agentKnowledgeSpace(tenantId, agentId, spaceId),
      {},
    ),
  removeAgentKnowledgeSpace: (tenantId: string, agentId: string, spaceId: string) =>
    http.delete<AgentKnowledgeSpaceBindings>(
      endpoints.admin.agentKnowledgeSpace(tenantId, agentId, spaceId),
      {},
    ),
  testAgentKnowledgeSearch: (
    tenantId: string,
    agentId: string,
    payload: AgentKnowledgeSearchTestRequest,
  ) =>
    http.post<AgentKnowledgeSearchTest>(
      endpoints.admin.agentKnowledgeSearchTest(tenantId, agentId),
      payload,
    ),
};
