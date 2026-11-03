import type { RunEventNodeData } from "./RunEventNode";

export type NodeTone = RunEventNodeData["tone"];

export function toolLabel(name: string, argumentsValue: Record<string, unknown>) {
  if (name === "capability_search") {
    return argumentsValue.action === "load" ? "加载 Skill / MCP" : "发现 Skill / MCP";
  }
  if (name === "capability_execute") return "执行 Skill / MCP";
  if (name === "knowledge_search") return "知识检索工具";
  return `工具：${name}`;
}

export function toolDetail(name: string, argumentsValue: Record<string, unknown>) {
  if (name === "capability_search") {
    const action = readString(argumentsValue, "action") || "find";
    const target =
      readString(argumentsValue, "skill_id") || readString(argumentsValue, "query") || "全部能力";
    return `action=${action} · ${target}`;
  }
  if (name === "capability_execute")
    return readString(argumentsValue, "skill_id") || "未记录能力 ID";
  return preview(JSON.stringify(argumentsValue));
}

export function toolIcon(name: string): RunEventNodeData["icon"] {
  return name === "knowledge_search" || name === "capability_search" ? "Search" : "ApplicationOne";
}

export function readRecord(data: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = data[key];
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function readList(data: Record<string, unknown>, key: string): unknown[] {
  const value = data[key];
  return Array.isArray(value) ? value : [];
}

export function readString(data: Record<string, unknown>, key: string) {
  return typeof data[key] === "string" ? data[key] : "";
}

export function readNumber(data: Record<string, unknown>, key: string) {
  return typeof data[key] === "number" ? data[key] : undefined;
}

export function preview(value: string) {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > 120 ? `${normalized.slice(0, 120)}…` : normalized;
}

export function timestamp(value: string | undefined) {
  const parsed = value ? Date.parse(value) : 0;
  return Number.isNaN(parsed) ? 0 : parsed;
}

export function entryLabel(value: string) {
  return value === "text" ? "文本入口" : value === "schedule" ? "定时入口" : value;
}

export function statusLabel(value: string) {
  return (
    { completed: "已完成", partial: "部分完成", failed: "失败", cancelled: "已取消" }[value] ??
    value
  );
}

export function statusTone(value: string): NodeTone {
  if (value === "completed") return "success";
  if (["failed", "cancelled"].includes(value)) return "danger";
  if (["partial", "running"].includes(value)) return "warning";
  return "default";
}

export function edgeColor(tone: NodeTone) {
  if (tone === "danger") return "#ff7875";
  if (tone === "success") return "#73d13d";
  if (tone === "warning") return "#69b1ff";
  return "#9aafc7";
}
