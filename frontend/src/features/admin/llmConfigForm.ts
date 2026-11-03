import type { LlmConfigConnectionTest, LlmConfigCreate, LlmConfigUpdate } from "@/shared/api/types";

export type LlmConfigForm = Omit<LlmConfigCreate, "api_key"> & {
  api_key?: string;
  status?: string;
};

export function createLlmConfigPayload(values: LlmConfigForm): LlmConfigCreate {
  return {
    name: values.name,
    provider: values.provider,
    model: values.model,
    base_url: values.base_url,
    api_key: values.api_key ?? "",
    temperature: values.temperature,
    max_tokens: values.max_tokens,
    thinking_enabled: values.thinking_enabled,
    prompt_cache_enabled: values.prompt_cache_enabled,
    is_default: values.is_default,
  };
}

export function updateLlmConfigPayload(values: LlmConfigForm): LlmConfigUpdate {
  const { api_key, ...rest } = values;
  return api_key ? { ...rest, api_key } : rest;
}

export function llmConnectionTestPayload(
  values: LlmConfigForm,
  configId?: string,
): LlmConfigConnectionTest {
  return {
    config_id: configId,
    provider: values.provider,
    model: values.model,
    base_url: values.base_url,
    api_key: values.api_key || undefined,
    temperature: values.temperature,
    max_tokens: values.max_tokens,
    thinking_enabled: values.thinking_enabled,
    prompt_cache_enabled: values.prompt_cache_enabled,
  };
}
