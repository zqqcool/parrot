export type ManifestFormValues = {
  execute: boolean;
  runtime: "python" | "node" | "shell";
  entrypoint: string;
  timeoutSeconds?: number;
  networkEnabled: boolean;
  env: { name?: string; value?: string }[];
};

type ParsedManifest = {
  values: ManifestFormValues | null;
  error: string | null;
};

export function parseManifest(content: string): ParsedManifest {
  try {
    const manifest = JSON.parse(content) as unknown;
    if (!isObject(manifest)) return { values: null, error: "manifest.json 必须是 JSON 对象。" };
    return { values: manifestValues(manifest), error: null };
  } catch {
    return { values: null, error: "manifest.json 不是有效的 JSON，请在 JSON 模式中修复后再保存。" };
  }
}

export function toManifest(values: ManifestFormValues): Record<string, unknown> {
  if (!values.execute) return { execute: false };
  const env = Object.fromEntries(
    (values.env ?? [])
      .filter((item) => item.name)
      .map((item) => [item.name ?? "", item.value ?? ""]),
  );
  return compact({
    execute: true,
    runtime: values.runtime,
    entrypoint: values.entrypoint,
    timeout_seconds: values.timeoutSeconds,
    network_enabled: values.networkEnabled || undefined,
    env: Object.keys(env).length ? env : undefined,
  });
}

export function manifestWarnings(values: ManifestFormValues, paths: string[]): string[] {
  if (!values.execute) return [];
  return [
    ...entrypointWarnings(values.entrypoint, paths),
    ...nodeWarnings(values.runtime, paths),
    ...envWarnings(values.env),
  ];
}

function manifestValues(manifest: Record<string, unknown>): ManifestFormValues {
  const legacyRuntime = legacyRuntimeValues(manifest);
  return {
    execute: isExecutable(manifest, legacyRuntime),
    runtime: runtimeValue(manifest, legacyRuntime),
    entrypoint: stringValue(manifest.entrypoint, legacyRuntime.entrypoint),
    timeoutSeconds: numberValue(manifest.timeout_seconds, legacyRuntime.timeout_seconds),
    networkEnabled: isNetworkEnabled(manifest),
    env: environmentValues(manifest, legacyRuntime),
  };
}

function legacyRuntimeValues(manifest: Record<string, unknown>): Record<string, unknown> {
  return isObject(manifest.runtime) ? manifest.runtime : {};
}

function isExecutable(
  manifest: Record<string, unknown>,
  legacyRuntime: Record<string, unknown>,
): boolean {
  return (
    manifest.execute === true ||
    (manifest.execute === undefined && typeof legacyRuntime.entrypoint === "string")
  );
}

function runtimeValue(
  manifest: Record<string, unknown>,
  legacyRuntime: Record<string, unknown>,
): ManifestFormValues["runtime"] {
  const runtime = typeof manifest.runtime === "string" ? manifest.runtime : legacyRuntime.type;
  return runtime === "node" || runtime === "shell" ? runtime : "python";
}

function isNetworkEnabled(manifest: Record<string, unknown>): boolean {
  const permissions = isObject(manifest.permissions) ? manifest.permissions : {};
  return manifest.network_enabled === true || permissions.network_enabled === true;
}

function environmentValues(
  manifest: Record<string, unknown>,
  legacyRuntime: Record<string, unknown>,
): ManifestFormValues["env"] {
  const env = isObject(manifest.env)
    ? manifest.env
    : isObject(legacyRuntime.env)
      ? legacyRuntime.env
      : {};
  return Object.entries(env).map(([name, value]) => ({ name, value: String(value) }));
}

function entrypointWarnings(entrypoint: string, paths: string[]): string[] {
  if (!entrypoint) return ["需要填写入口文件。"];
  return paths.length > 0 && !paths.includes(entrypoint) ? ["入口文件尚未存在于当前草稿。"] : [];
}

function nodeWarnings(runtime: ManifestFormValues["runtime"], paths: string[]): string[] {
  if (runtime !== "node") return [];
  return [
    paths.includes("package.json") ? undefined : "Node Skill 需要根目录 package.json。",
    paths.includes("package-lock.json") ? undefined : "Node Skill 需要根目录 package-lock.json。",
  ].filter((item): item is string => Boolean(item));
}

function envWarnings(env: ManifestFormValues["env"]): string[] {
  const reserved = (env ?? []).find((item) => isReservedEnv(item.name));
  return reserved?.name ? [`${reserved.name} 是受保留保护的环境变量，后端会拒绝保存。`] : [];
}

function stringValue(current: unknown, legacy: unknown): string {
  if (typeof current === "string") return current;
  return typeof legacy === "string" ? legacy : "";
}

function numberValue(current: unknown, legacy: unknown): number | undefined {
  if (typeof current === "number") return current;
  return typeof legacy === "number" ? legacy : undefined;
}

function compact(value: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined));
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isReservedEnv(name: string | undefined): boolean {
  return Boolean(
    name &&
    (name === "PATH" ||
      name === "HOME" ||
      name.startsWith("PARROT_") ||
      name.startsWith("LD_") ||
      name.startsWith("DYLD_") ||
      name.startsWith("PYTHON") ||
      name.startsWith("NODE_")),
  );
}
