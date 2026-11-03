import { endpoints } from "@/shared/api/endpoints";
import { withSearchQuery } from "@/shared/api/query";
import { http } from "@/shared/api/transport";
import type {
  EmbeddingConfig,
  EmbeddingConfigConnectionTest,
  EmbeddingConfigCreate,
  EmbeddingConfigUpdate,
  LlmConfig,
  LlmConfigConnectionTest,
  LlmConfigCreate,
  LlmConfigUpdate,
  ModelConnectionTest,
  ModelProvider,
  RerankerConfig,
  RerankerConfigConnectionTest,
  RerankerConfigCreate,
  RerankerConfigUpdate,
} from "@/shared/api/types";

const MODEL_CONNECTION_TEST_TIMEOUT_MS = 35_000;

export const modelConfigAdminApi = {
  listLlmConfigs: (tenantId: string, query = "") =>
    http.get<LlmConfig[]>(withSearchQuery(endpoints.admin.llmConfigs(tenantId), query)),
  createLlmConfig: (tenantId: string, payload: LlmConfigCreate) =>
    http.post<LlmConfig>(endpoints.admin.llmConfigs(tenantId), payload),
  updateLlmConfig: (tenantId: string, configId: string, payload: LlmConfigUpdate) =>
    http.patch<LlmConfig>(endpoints.admin.llmConfig(tenantId, configId), payload),
  testLlmConfigDraftConnection: (tenantId: string, payload: LlmConfigConnectionTest) =>
    http.post<ModelConnectionTest>(
      endpoints.admin.llmConfigDraftConnectionTest(tenantId),
      payload,
      {
        timeoutMs: MODEL_CONNECTION_TEST_TIMEOUT_MS,
      },
    ),
  listModelProviders: (tenantId: string) =>
    http.get<ModelProvider[]>(endpoints.admin.modelProviders(tenantId)),
  listEmbeddingConfigs: (tenantId: string, query = "") =>
    http.get<EmbeddingConfig[]>(withSearchQuery(endpoints.admin.embeddingConfigs(tenantId), query)),
  createEmbeddingConfig: (tenantId: string, payload: EmbeddingConfigCreate) =>
    http.post<EmbeddingConfig>(endpoints.admin.embeddingConfigs(tenantId), payload),
  updateEmbeddingConfig: (tenantId: string, configId: string, payload: EmbeddingConfigUpdate) =>
    http.patch<EmbeddingConfig>(endpoints.admin.embeddingConfig(tenantId, configId), payload),
  deleteEmbeddingConfig: (tenantId: string, configId: string) =>
    http.delete<{ deleted: boolean }>(endpoints.admin.embeddingConfig(tenantId, configId), {}),
  testEmbeddingConfigDraftConnection: (tenantId: string, payload: EmbeddingConfigConnectionTest) =>
    http.post<ModelConnectionTest>(
      endpoints.admin.embeddingConfigDraftConnectionTest(tenantId),
      payload,
      { timeoutMs: MODEL_CONNECTION_TEST_TIMEOUT_MS },
    ),
  listRerankerConfigs: (tenantId: string, query = "") =>
    http.get<RerankerConfig[]>(withSearchQuery(endpoints.admin.rerankerConfigs(tenantId), query)),
  createRerankerConfig: (tenantId: string, payload: RerankerConfigCreate) =>
    http.post<RerankerConfig>(endpoints.admin.rerankerConfigs(tenantId), payload),
  updateRerankerConfig: (tenantId: string, configId: string, payload: RerankerConfigUpdate) =>
    http.patch<RerankerConfig>(endpoints.admin.rerankerConfig(tenantId, configId), payload),
  testRerankerConfigDraftConnection: (tenantId: string, payload: RerankerConfigConnectionTest) =>
    http.post<ModelConnectionTest>(
      endpoints.admin.rerankerConfigDraftConnectionTest(tenantId),
      payload,
      { timeoutMs: MODEL_CONNECTION_TEST_TIMEOUT_MS },
    ),
};
