import { MarkerType, type Edge } from "@xyflow/react";

import type { Run, RunEvent } from "@/shared/api/types";

import type { RunEventFlowNode, RunEventNodeData } from "./RunEventNode";

const columns = 3;
const nodeWidth = 304;
const nodeHeight = 190;

type NodeTone = RunEventNodeData["tone"];

type TraceNode = RunEventNodeData & {
  id: string;
  order: number;
};

type TraceNodeInput = Omit<TraceNode, "eventId" | "occurredAt" | "sequence"> & {
  event?: RunEvent;
  occurredAt?: string;
  sequence?: number;
};

export function createRunEventGraph(run: Run, events: RunEvent[], selectedEventId?: string) {
  const traces = [
    createEntryNode(run, events),
    createInputNode(run, events),
    ...createAgentLoopNodes(events),
    createOutputNode(events),
    createStatusNode(run, events),
  ]
    .filter((item): item is TraceNode => item !== null)
    .sort((left, right) => left.order - right.order);
  const nodes: RunEventFlowNode[] = traces.map((trace, index) => ({
    id: trace.id,
    type: "runEvent",
    position: {
      x: (index % columns) * nodeWidth,
      y: Math.floor(index / columns) * nodeHeight,
    },
    data: trace,
    selected: trace.eventId === selectedEventId,
  }));
  const edges = nodes.slice(1).map((node, index) => createEdge(nodes[index], node));
  return { nodes, edges };
}

function createEntryNode(run: Run, events: RunEvent[]): TraceNode {
  const event = findFirst(events, "ai.interaction.accepted") ?? events[0];
  return traceNode({
    id: `entry-${run.id}`,
    event,
    label: "入口请求",
    eventType: run.entry_type,
    detail: `${entryLabel(run.entry_type)} · ${run.requester.display_name}`,
    state: "已接收",
    icon: "Message",
    tone: "default",
    order: event?.sequence ?? 0,
  });
}

function createInputNode(run: Run, events: RunEvent[]): TraceNode {
  const event = findFirst(events, "ai.input.processed");
  return traceNode({
    id: `input-${run.id}`,
    event,
    label: "用户提示词",
    eventType: "ai.input.processed",
    detail: preview(run.input_summary || "未记录文本输入"),
    state: event ? "已送入 Agent Loop" : "等待处理",
    icon: "Message",
    tone: "warning",
    modelInput: {
      entryType: run.entry_type,
      inputType: run.input_type,
      userPrompt: run.input_summary || "未记录文本输入",
    },
    order: event?.sequence ?? 1,
  });
}

function createAgentLoopNodes(events: RunEvent[]): TraceNode[] {
  const completedTools = completedToolsById(events);
  return events.flatMap((event) => {
    if (event.type === "ai.interaction.status") return [statusEventNode(event)];
    if (event.type === "ai.agent.plan.created") return [planNode(event)];
    if (event.type === "ai.agent.todo.updated") return [todoNode(event)];
    if (event.type === "ai.knowledge.intent.analyzed") return [knowledgeIntentNode(event)];
    if (event.type === "ai.knowledge.retrieved") return [knowledgeRetrievalNode(event)];
    if (event.type === "ai.tool.started")
      return [toolNode(event, completedTools.get(readString(event, "tool_call_id")))];
    return [];
  });
}

function statusEventNode(event: RunEvent): TraceNode {
  const status = readString(event, "status") || "running";
  return traceNode({
    id: `status-event-${event.event_id}`,
    event,
    label: "Agent Loop",
    eventType: event.type,
    detail: "运行时已开始执行",
    state: statusLabel(status),
    icon: "RobotOne",
    tone: "warning",
    order: event.sequence,
  });
}

function planNode(event: RunEvent): TraceNode {
  const action = readString(event, "action") || "未记录";
  return traceNode({
    id: `plan-${event.event_id}`,
    event,
    label: "执行规划",
    eventType: event.type,
    detail: `计划动作：${action}`,
    state: readBoolean(event, "synthetic") ? "规则生成" : "模型生成",
    icon: "RobotOne",
    tone: "warning",
    order: event.sequence,
  });
}

function todoNode(event: RunEvent): TraceNode {
  return traceNode({
    id: `todo-${event.event_id}`,
    event,
    label: "任务更新",
    eventType: event.type,
    detail: "Agent Loop 更新执行任务",
    state: "已记录",
    icon: "History",
    tone: "default",
    order: event.sequence,
  });
}

function knowledgeIntentNode(event: RunEvent): TraceNode {
  const clarification = readBoolean(event, "requires_clarification");
  return traceNode({
    id: `knowledge-intent-${event.event_id}`,
    event,
    label: "知识意图分析",
    eventType: event.type,
    detail: clarification ? "需要补充用户问题" : "已识别检索意图",
    state: readBoolean(event, "fallback_used") ? "回退策略" : "完成",
    icon: "Search",
    tone: clarification ? "warning" : "default",
    order: event.sequence,
  });
}

function knowledgeRetrievalNode(event: RunEvent): TraceNode {
  const count = readNumber(event, "citation_count");
  return traceNode({
    id: `knowledge-retrieval-${event.event_id}`,
    event,
    label: "知识检索",
    eventType: event.type,
    detail: `${readString(event, "retrieval_method") || "默认检索"} · ${count ?? 0} 条引用`,
    state: readString(event, "status") || "完成",
    icon: "Search",
    tone: "default",
    order: event.sequence,
  });
}

function toolNode(started: RunEvent, completed?: RunEvent): TraceNode {
  const name = readString(started, "name") || "未命名工具";
  return traceNode({
    id: `tool-${started.event_id}`,
    event: completed ?? started,
    label: "工具调用",
    eventType: completed?.type ?? started.type,
    detail: name,
    state: readString(completed, "status") || (completed ? "完成" : "执行中"),
    icon: "ApplicationOne",
    tone: completed ? "success" : "warning",
    order: started.sequence,
  });
}

function createOutputNode(events: RunEvent[]): TraceNode | null {
  const completed = findLast(events, "ai.output.completed");
  const latestDelta = findLast(events, "ai.output.delta");
  const event = completed ?? latestDelta;
  if (!event) return null;
  const content = readString(completed, "content") || "正在接收模型流式输出";
  return traceNode({
    id: `output-${event.event_id}`,
    event,
    label: "模型输出",
    eventType: event.type,
    detail: preview(content),
    state: readString(completed, "runtime_status") || "生成中",
    icon: "Send",
    tone: completed ? "success" : "warning",
    order: event.sequence,
  });
}

function createStatusNode(run: Run, events: RunEvent[]): TraceNode {
  const event = events[events.length - 1];
  return traceNode({
    id: `final-status-${run.id}`,
    event,
    label: "运行状态",
    eventType: event?.type ?? "run.status",
    detail: `${run.agent_name} · ${entryLabel(run.entry_type)}`,
    state: statusLabel(run.status),
    icon: run.status === "failed" || run.status === "cancelled" ? "OffScreen" : "ApplicationOne",
    tone: statusTone(run.status),
    order: (event?.sequence ?? 0) + 1,
  });
}

function traceNode({ event, occurredAt, sequence, ...input }: TraceNodeInput): TraceNode {
  return {
    ...input,
    eventId: event?.event_id,
    occurredAt: occurredAt ?? event?.occurred_at ?? "",
    sequence: sequence ?? event?.sequence,
  };
}

function createEdge(source: RunEventFlowNode, target: RunEventFlowNode): Edge {
  return {
    id: `edge-${source.id}-${target.id}`,
    source: source.id,
    target: target.id,
    type: "smoothstep",
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: edgeColor(target.data.tone),
      width: 14,
      height: 14,
    },
    style: { stroke: edgeColor(target.data.tone), strokeWidth: 1.3 },
  };
}

function completedToolsById(events: RunEvent[]) {
  return new Map(
    events
      .filter((event) => event.type === "ai.tool.completed")
      .map((event) => [readString(event, "tool_call_id"), event]),
  );
}

function findFirst(events: RunEvent[], type: string) {
  return events.find((event) => event.type === type);
}

function findLast(events: RunEvent[], type: string) {
  return [...events].reverse().find((event) => event.type === type);
}

function readString(event: RunEvent | undefined, key: string) {
  const value = event?.data[key];
  return typeof value === "string" ? value : "";
}

function readNumber(event: RunEvent, key: string) {
  const value = event.data[key];
  return typeof value === "number" ? value : undefined;
}

function readBoolean(event: RunEvent, key: string) {
  return event.data[key] === true;
}

function preview(value: string) {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > 120 ? `${normalized.slice(0, 120)}…` : normalized;
}

function entryLabel(value: string) {
  return value === "text" ? "文本入口" : value === "schedule" ? "定时入口" : value;
}

function statusLabel(value: string) {
  if (value === "completed") return "已完成";
  if (value === "partial") return "部分完成";
  if (value === "failed") return "失败";
  if (value === "cancelled") return "已取消";
  if (value === "running") return "执行中";
  return value || "已记录";
}

function statusTone(value: string): NodeTone {
  if (value === "completed") return "success";
  if (["failed", "cancelled"].includes(value)) return "danger";
  if (["partial", "running"].includes(value)) return "warning";
  return "default";
}

function edgeColor(tone: NodeTone) {
  if (tone === "danger") return "#ff7875";
  if (tone === "success") return "#73d13d";
  if (tone === "warning") return "#69b1ff";
  return "#9aafc7";
}
