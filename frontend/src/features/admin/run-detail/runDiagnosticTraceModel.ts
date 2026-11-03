export type ModelRequestSnapshot = {
  messages: Record<string, unknown>[];
  tools: Record<string, unknown>[];
};

export function modelRequestSnapshot(
  data: Record<string, unknown>,
): ModelRequestSnapshot | undefined {
  const raw = record(data.request_snapshot);
  if (raw.format !== "openai-compatible.chat-completions.v1") return undefined;
  return { messages: records(raw.messages), tools: records(raw.tools) };
}

export function modelRequestMessageCount(
  data: Record<string, unknown>,
  snapshot = modelRequestSnapshot(data),
) {
  return number(data.message_count) ?? snapshot?.messages.length ?? 0;
}

export function modelRequestToolCount(
  data: Record<string, unknown>,
  snapshot = modelRequestSnapshot(data),
) {
  return list(data.tool_names).length || snapshot?.tools.length || 0;
}

export function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function records(value: unknown): Record<string, unknown>[] {
  return list(value).map(record);
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function number(value: unknown) {
  return typeof value === "number" ? value : undefined;
}
