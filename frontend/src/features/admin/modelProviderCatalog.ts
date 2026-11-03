import type { ModelProvider, ModelProviderCapability } from "@/shared/api/types";

export type ModelCapabilityKind = ModelProviderCapability["kind"];

export function providerCapability(
  providers: ModelProvider[],
  providerKey: string | undefined,
  kind: ModelCapabilityKind,
): ModelProviderCapability | undefined {
  return providers
    .find((provider) => provider.key === providerKey)
    ?.capabilities.find((capability) => capability.kind === kind);
}

export function providerOptions(
  providers: ModelProvider[],
  kind: ModelCapabilityKind,
  currentProvider?: string,
) {
  const options = providers
    .filter((provider) => provider.capabilities.some((capability) => capability.kind === kind))
    .map((provider) => ({ value: provider.key, label: provider.name }));
  if (currentProvider && !options.some((option) => option.value === currentProvider)) {
    options.push({ value: currentProvider, label: `${currentProvider}（存量配置）` });
  }
  return options;
}

export function providerDefaultValues(capability: ModelProviderCapability | undefined) {
  return {
    ...(capability?.default_base_url ? { base_url: capability.default_base_url } : {}),
    ...(capability?.default_model ? { model: capability.default_model } : {}),
    ...(capability?.default_embedding_dimension
      ? { embedding_dimension: capability.default_embedding_dimension }
      : {}),
  };
}

export function providerDisplayName(providers: ModelProvider[], providerKey: string): string {
  return providers.find((provider) => provider.key === providerKey)?.name ?? providerKey;
}
