import { MarkerType, type Edge } from "@xyflow/react";

import type { Run, RunDiagnosticTrace, RunEvent } from "@/shared/api/types";

import type { RunEventFlowNode, RunEventNodeData } from "./RunEventNode";
import {
  edgeColor,
  entryLabel,
  preview,
  readNumber,
  readRecord,
  readString,
  statusLabel,
  statusTone,
  timestamp,
  toolIcon,
  toolLabel,
} from "./runTraceGraphHelpers";
import {
  modelRequestMessageCount,
  modelRequestSnapshot,
  modelRequestToolCount,
} from "./runDiagnosticTraceModel";

const columns = 4;
const nodeWidth = 304;
const nodeHeight = 190;

type TraceNode = RunEventNodeData & { id: string; order: number; priority: number };

export function createRunTraceGraph(
  run: Run,
  events: RunEvent[],
  diagnostics: RunDiagnosticTrace[],
  selectedEventId?: string,
) {
  const traces = [
    entryNode(run, events),
    inputNode(run, events),
    ...eventNodes(events, diagnostics),
    ...diagnosticNodes(diagnostics),
    outputNode(events),
    finalNode(run, events),
  ]
    .filter((item): item is TraceNode => item !== null)
    .sort((left, right) => left.order - right.order || left.priority - right.priority);
  const nodes: RunEventFlowNode[] = traces.map((trace, index) => ({
    id: trace.id,
    type: "runEvent",
    position: { x: (index % columns) * nodeWidth, y: Math.floor(index / columns) * nodeHeight },
    data: trace,
    selected: trace.eventId === selectedEventId,
  }));
  return { nodes, edges: nodes.slice(1).map((node, index) => edge(nodes[index], node)) };
}

function entryNode(run: Run, events: RunEvent[]): TraceNode {
  const event = events.find((item) => item.type === "ai.interaction.accepted") ?? events[0];
  return fromEvent(
    `entry-${run.id}`,
    event,
    {
      label: "入口请求",
      eventType: run.entry_type,
      detail: `${entryLabel(run.entry_type)} · ${run.requester.display_name}`,
      state: "已接收",
      icon: "Message",
      tone: "default",
    },
    0,
  );
}

function inputNode(run: Run, events: RunEvent[]): TraceNode {
  const event = events.find((item) => item.type === "ai.input.processed");
  return fromEvent(
    `input-${run.id}`,
    event,
    {
      label: "用户输入",
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
    },
    1,
  );
}

function eventNodes(events: RunEvent[], diagnostics: RunDiagnosticTrace[]): TraceNode[] {
  const hasToolDiagnostics = diagnostics.some((item) => item.type === "tool.call");
  return events.flatMap((event) => {
    if (event.type === "ai.interaction.status") return [statusNode(event)];
    if (event.type === "ai.agent.plan.created") return [planNode(event)];
    if (event.type === "ai.agent.todo.updated") return [todoNode(event)];
    if (event.type === "ai.knowledge.intent.analyzed") return [intentNode(event)];
    if (event.type === "ai.knowledge.retrieved") return [retrievalNode(event)];
    if (event.type === "ai.tool.started" && !hasToolDiagnostics) return [legacyToolNode(event)];
    return [];
  });
}

function statusNode(event: RunEvent): TraceNode {
  return fromEvent(
    `status-${event.event_id}`,
    event,
    {
      label: "Agent Loop",
      eventType: event.type,
      detail: "运行时已开始执行",
      state: readString(event.data, "status") || "运行中",
      icon: "RobotOne",
      tone: "warning",
    },
    2,
  );
}

function planNode(event: RunEvent): TraceNode {
  const action = readString(event.data, "action") || "未记录";
  return fromEvent(
    `plan-${event.event_id}`,
    event,
    {
      label: "执行规划",
      eventType: event.type,
      detail: `计划动作：${action}`,
      state: event.data.synthetic === true ? "规则生成" : "模型生成",
      icon: "RobotOne",
      tone: "warning",
    },
    4,
  );
}

function todoNode(event: RunEvent): TraceNode {
  return fromEvent(
    `todo-${event.event_id}`,
    event,
    {
      label: "任务更新",
      eventType: event.type,
      detail: "Agent Loop 更新执行任务",
      state: "已记录",
      icon: "History",
      tone: "default",
    },
    4,
  );
}

function intentNode(event: RunEvent): TraceNode {
  const clarification = event.data.requires_clarification === true;
  return fromEvent(
    `knowledge-intent-${event.event_id}`,
    event,
    {
      label: "知识意图分析",
      eventType: event.type,
      detail: clarification ? "需要补充用户问题" : "已识别检索意图",
      state: event.data.fallback_used === true ? "回退策略" : "完成",
      icon: "Search",
      tone: clarification ? "warning" : "default",
    },
    4,
  );
}

function retrievalNode(event: RunEvent): TraceNode {
  return fromEvent(
    `knowledge-retrieval-${event.event_id}`,
    event,
    {
      label: "知识检索",
      eventType: event.type,
      detail: `${readString(event.data, "retrieval_method") || "默认检索"} · ${readNumber(event.data, "citation_count") ?? 0} 条引用`,
      state: readString(event.data, "status") || "完成",
      icon: "Search",
      tone: "default",
    },
    4,
  );
}

function legacyToolNode(event: RunEvent): TraceNode {
  return fromEvent(
    `tool-${event.event_id}`,
    event,
    {
      label: "工具调用",
      eventType: event.type,
      detail: readString(event.data, "name") || "未命名工具",
      state: "执行中",
      icon: "ApplicationOne",
      tone: "warning",
    },
    5,
  );
}

function diagnosticNodes(items: RunDiagnosticTrace[]): TraceNode[] {
  return items.flatMap((item) => {
    if (item.type === "model.request") return [modelRequestNode(item)];
    if (item.type === "tool.call") return [toolCallNode(item)];
    if (item.type === "tool.result") return [toolResultNode(item)];
    return [];
  });
}

function modelRequestNode(trace: RunDiagnosticTrace): TraceNode {
  const data = trace.data;
  const snapshot = modelRequestSnapshot(data);
  const llm = readRecord(data, "llm");
  return fromTrace(trace, {
    label: "模型请求",
    eventType: `model.${readString(data, "phase") || "completion"}`,
    detail: `${modelRequestMessageCount(data, snapshot)} 条 messages · ${modelRequestToolCount(data, snapshot)} 个工具定义`,
    state: `${readString(llm, "provider") || "LLM"} / ${readString(llm, "model") || "未记录模型"}`,
    icon: "RobotOne",
    tone: "warning",
  });
}

function toolCallNode(trace: RunDiagnosticTrace): TraceNode {
  const data = trace.data;
  const name = readString(data, "name") || "未命名工具";
  return fromTrace(trace, {
    label: toolLabel(name, {}),
    eventType: "tool.call",
    detail: `${readNumber(data, "argument_count") ?? 0} 个参数（原值仅在本地请求快照中保留）`,
    state: "已提交执行",
    icon: toolIcon(name),
    tone: "warning",
  });
}

function toolResultNode(trace: RunDiagnosticTrace): TraceNode {
  const data = trace.data;
  const name = readString(data, "name") || "未命名工具";
  const status = readString(data, "status") || "已完成";
  return fromTrace(trace, {
    label: `${toolLabel(name, {})} 结果`,
    eventType: "tool.result",
    detail: readString(data, "code") || "原始结果仅在本地请求快照中保留",
    state: status,
    icon: toolIcon(name),
    tone: ["failed", "rejected"].includes(status) ? "danger" : "success",
  });
}

function outputNode(events: RunEvent[]): TraceNode | null {
  const event = latestOutputEvent(events);
  if (!event) return null;
  const completed = event.type === "ai.output.completed" ? event : undefined;
  return fromEvent(
    `output-${event.event_id}`,
    event,
    {
      label: "模型输出",
      eventType: event.type,
      detail: outputDetail(completed),
      state: outputState(completed),
      icon: "Send",
      tone: completed ? "success" : "warning",
    },
    8,
  );
}

function latestOutputEvent(events: RunEvent[]) {
  const reversed = [...events].reverse();
  return (
    reversed.find((item) => item.type === "ai.output.completed") ??
    reversed.find((item) => item.type === "ai.output.delta")
  );
}

function outputDetail(event: RunEvent | undefined) {
  if (!event) return "正在接收模型流式输出";
  return preview(readString(event.data, "content") || "正在接收模型流式输出");
}

function outputState(event: RunEvent | undefined) {
  return event ? readString(event.data, "runtime_status") || "生成中" : "生成中";
}

function finalNode(run: Run, events: RunEvent[]): TraceNode {
  const event = events[events.length - 1];
  return fromEvent(
    `final-${run.id}`,
    event,
    {
      label: "运行状态",
      eventType: event?.type ?? "run.status",
      detail: `${run.agent_name} · ${entryLabel(run.entry_type)}`,
      state: statusLabel(run.status),
      icon: ["failed", "cancelled"].includes(run.status) ? "OffScreen" : "ApplicationOne",
      tone: statusTone(run.status),
    },
    9,
  );
}

function fromEvent(
  id: string,
  event: RunEvent | undefined,
  data: Omit<RunEventNodeData, "eventId" | "occurredAt" | "sequence">,
  priority: number,
): TraceNode {
  return {
    id,
    ...data,
    eventId: event?.event_id,
    occurredAt: event?.occurred_at ?? "",
    sequence: event?.sequence,
    order: timestamp(event?.occurred_at),
    priority,
  };
}

function fromTrace(
  trace: RunDiagnosticTrace,
  data: Omit<RunEventNodeData, "eventId" | "occurredAt" | "sequence">,
): TraceNode {
  return {
    id: `diagnostic-${trace.id}`,
    ...data,
    traceId: trace.id,
    occurredAt: trace.occurred_at,
    sequence: trace.sequence,
    diagnosticTrace: trace,
    order: timestamp(trace.occurred_at),
    priority: trace.type === "model.request" ? 3 : trace.type === "tool.call" ? 5 : 6,
  };
}

function edge(source: RunEventFlowNode, target: RunEventFlowNode): Edge {
  const color = edgeColor(target.data.tone);
  return {
    id: `edge-${source.id}-${target.id}`,
    source: source.id,
    target: target.id,
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
    style: { stroke: color, strokeWidth: 1.3 },
  };
}
