import { providerCapability, providerDefaultValues, providerOptions } from "./modelProviderCatalog";
import type { EmbeddingConfig, ModelProvider, RerankerConfig } from "@/shared/api/types";

export type ConfigKind = "embedding" | "reranker";
export type RetrievalConfig = EmbeddingConfig | RerankerConfig;
export type RetrievalConfigForm = {
  name: string;
  provider: string;
  model: string;
  base_url: string;
  api_key?: string;
  access_key_id?: string;
  secret_access_key?: string;
  embedding_dimension?: number;
  status?: "active" | "disabled";
};

export const statusOptions = [
  { value: "all", label: "全部状态" },
  { value: "active", label: "启用" },
  { value: "disabled", label: "停用" },
];

export function configLabel(kind: ConfigKind): string {
  return kind === "embedding" ? "Embedding" : "重排序";
}

export function defaultValues(kind: ConfigKind, providers: ModelProvider[]): RetrievalConfigForm {
  const provider = providerOptions(providers, kind)[0]?.value ?? "";
  const defaults = providerDefaultValues(providerCapability(providers, provider, kind));
  return {
    name: "",
    provider,
    model: "",
    base_url: "",
    ...(kind === "embedding" ? { embedding_dimension: 1024 } : {}),
    ...defaults,
  };
}

export function formValues(config: RetrievalConfig): RetrievalConfigForm {
  return {
    name: config.name,
    provider: config.provider,
    model: config.model,
    base_url: config.base_url,
    embedding_dimension: "embedding_dimension" in config ? config.embedding_dimension : undefined,
    status: config.status === "disabled" ? "disabled" : "active",
  };
}
