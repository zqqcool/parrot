import type { Run, RunEvent } from "@/shared/api/types";
import { formatDateTime, formatDuration } from "@/shared/time";

export type RunMetric = { label: string; value: string };

export function getRunOutput(events: RunEvent[]) {
  const completed = [...events].reverse().find((event) => event.type === "ai.output.completed");
  const content = completed ? readContent(completed) : "";
  if (content) return content;
  return currentOutputDeltas(events).join("");
}

export function getRunMetrics(run: Run, events: RunEvent[]): RunMetric[] {
  const outputEvents = events.filter((event) => event.type.startsWith("ai.output.")).length;
  return [
    { label: "事件数", value: String(events.length) },
    { label: "输出事件", value: String(outputEvents) },
    { label: "最后序号", value: String(events[events.length - 1]?.sequence ?? 0) },
    { label: "执行耗时", value: formatDuration(run.created_at, run.updated_at) },
  ];
}

export const formatRunTime = formatDateTime;

export function statusColor(value: string) {
  if (value === "completed") return "success";
  if (["failed", "cancelled"].includes(value)) return "error";
  if (value === "partial") return "warning";
  return "processing";
}

export function socketStateLabel(value: string) {
  if (value === "connected") return "已连接";
  if (value === "connecting") return "连接中";
  return "未连接";
}

export function formatEventPayload(data: Record<string, unknown>) {
  return JSON.stringify(data, null, 2);
}

function readDelta(event: RunEvent) {
  return typeof event.data.delta === "string" ? event.data.delta : "";
}

function readContent(event: RunEvent) {
  return typeof event.data.content === "string" ? event.data.content : "";
}

function currentOutputDeltas(events: RunEvent[]) {
  let deltas: string[] = [];
  for (const event of events) {
    if (event.type === "ai.output.reset") deltas = [];
    if (event.type === "ai.output.delta") deltas.push(readDelta(event));
  }
  return deltas;
}
