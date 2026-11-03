import type { KnowledgeMergeSettingsUpdate, RerankerConfig } from "@/shared/api/types";

export function mergeSettingsFormValues(settings: {
  merge_rerank_enabled: boolean;
  reranker_config_id: string | null;
  rerank_top_n: number;
  result_top_k: number;
  min_rerank_score: number | null;
}): KnowledgeMergeSettingsUpdate {
  return {
    merge_rerank_enabled: settings.merge_rerank_enabled,
    reranker_config_id: settings.reranker_config_id ?? undefined,
    rerank_top_n: settings.rerank_top_n,
    result_top_k: settings.result_top_k,
    min_rerank_score: settings.min_rerank_score ?? undefined,
  };
}

export function completeMergeSettingsPayload(
  values: KnowledgeMergeSettingsUpdate,
): KnowledgeMergeSettingsUpdate {
  if (values.merge_rerank_enabled) return values;
  return {
    ...values,
    reranker_config_id: null,
    min_rerank_score: null,
  };
}

export function activeRerankerConfigs(configs: RerankerConfig[] | undefined): RerankerConfig[] {
  return (configs ?? []).filter((config) => config.status === "active");
}
