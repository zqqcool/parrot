import { adminApi } from "@/shared/api/client";
import type {
  EmbeddingConfigCreate,
  EmbeddingConfigConnectionTest,
  EmbeddingConfigUpdate,
  ModelConnectionTest,
  RerankerConfigCreate,
  RerankerConfigConnectionTest,
  RerankerConfigUpdate,
} from "@/shared/api/types";

import type { ConfigKind, RetrievalConfig, RetrievalConfigForm } from "./retrievalModelConfigTypes";

export function listConfigs(
  kind: ConfigKind,
  tenantId: string,
  query: string,
): Promise<RetrievalConfig[]> {
  return kind === "embedding"
    ? adminApi.listEmbeddingConfigs(tenantId, query)
    : adminApi.listRerankerConfigs(tenantId, query);
}

export function createConfig(
  kind: ConfigKind,
  tenantId: string,
  values: RetrievalConfigForm,
): Promise<RetrievalConfig> {
  return kind === "embedding"
    ? adminApi.createEmbeddingConfig(tenantId, embeddingCreatePayload(values))
    : adminApi.createRerankerConfig(tenantId, rerankerCreatePayload(values));
}

export function updateConfig(
  kind: ConfigKind,
  tenantId: string,
  configId: string,
  values: RetrievalConfigForm,
): Promise<RetrievalConfig> {
  return kind === "embedding"
    ? adminApi.updateEmbeddingConfig(tenantId, configId, embeddingUpdatePayload(values))
    : adminApi.updateRerankerConfig(tenantId, configId, rerankerUpdatePayload(values));
}

export function deleteEmbeddingConfig(
  tenantId: string,
  configId: string,
): Promise<{ deleted: boolean }> {
  return adminApi.deleteEmbeddingConfig(tenantId, configId);
}

export function testConfigConnection(
  kind: ConfigKind,
  tenantId: string,
  values: RetrievalConfigForm,
  configId?: string,
): Promise<ModelConnectionTest> {
  return kind === "embedding"
    ? adminApi.testEmbeddingConfigDraftConnection(
        tenantId,
        embeddingConnectionPayload(values, configId),
      )
    : adminApi.testRerankerConfigDraftConnection(
        tenantId,
        rerankerConnectionPayload(values, configId),
      );
}

function embeddingCreatePayload(values: RetrievalConfigForm): EmbeddingConfigCreate {
  return {
    name: values.name,
    provider: values.provider,
    model: values.model,
    base_url: values.base_url,
    api_key: values.api_key ?? "",
    embedding_dimension: values.embedding_dimension ?? 1024,
  };
}

function rerankerCreatePayload(values: RetrievalConfigForm): RerankerConfigCreate {
  return withoutBlankCredentials({
    name: values.name,
    provider: values.provider,
    model: values.model,
    base_url: values.base_url,
    api_key: values.api_key,
    access_key_id: values.access_key_id,
    secret_access_key: values.secret_access_key,
  });
}

function embeddingUpdatePayload(values: RetrievalConfigForm): EmbeddingConfigUpdate {
  return withoutBlankApiKey({
    name: values.name,
    provider: values.provider,
    model: values.model,
    base_url: values.base_url,
    api_key: values.api_key,
    embedding_dimension: values.embedding_dimension,
    status: values.status,
  });
}

function rerankerUpdatePayload(values: RetrievalConfigForm): RerankerConfigUpdate {
  return withoutBlankCredentials({
    name: values.name,
    provider: values.provider,
    model: values.model,
    base_url: values.base_url,
    api_key: values.api_key,
    access_key_id: values.access_key_id,
    secret_access_key: values.secret_access_key,
    status: values.status,
  });
}

function embeddingConnectionPayload(
  values: RetrievalConfigForm,
  configId?: string,
): EmbeddingConfigConnectionTest {
  return {
    config_id: configId,
    provider: values.provider,
    model: values.model,
    base_url: values.base_url,
    api_key: values.api_key || undefined,
    embedding_dimension: values.embedding_dimension ?? 1024,
  };
}

function rerankerConnectionPayload(
  values: RetrievalConfigForm,
  configId?: string,
): RerankerConfigConnectionTest {
  return withoutBlankCredentials({
    config_id: configId,
    provider: values.provider,
    model: values.model,
    base_url: values.base_url,
    api_key: values.api_key || undefined,
    access_key_id: values.access_key_id || undefined,
    secret_access_key: values.secret_access_key || undefined,
  });
}

function withoutBlankApiKey<T extends { api_key?: string }>(values: T): T {
  return values.api_key ? values : { ...values, api_key: undefined };
}

function withoutBlankCredentials<
  T extends { api_key?: string; access_key_id?: string; secret_access_key?: string },
>(values: T): T {
  return {
    ...values,
    api_key: values.api_key || undefined,
    access_key_id: values.access_key_id || undefined,
    secret_access_key: values.secret_access_key || undefined,
  };
}
