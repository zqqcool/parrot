import { describe, expect, it } from "vitest";

import type { Run, RunDiagnosticTrace, RunEvent } from "@/shared/api/types";

import { createRunEventGraph } from "./runEventGraph";
import { createRunTraceGraph } from "./runTraceGraph";
import { getRunMetrics, getRunOutput } from "./runDetailModel";

const run: Run = {
  id: "interaction_test",
  tenant_id: "tenant_test",
  agent_id: "agent_test",
  agent_name: "Demo Agent",
  actor_type: "user",
  requester: { actor_type: "user", actor_id: "user_test", display_name: "测试用户" },
  entry_type: "text",
  input_type: "text",
  input_summary: "你好",
  status: "completed",
  runtime_execution_id: "runtime_test",
  created_at: "2026-07-14T09:00:00.000Z",
  updated_at: "2026-07-14T09:00:02.500Z",
};

const events: RunEvent[] = [
  {
    event_id: "event_1",
    type: "ai.interaction.accepted",
    request_id: "req_test",
    occurred_at: "2026-07-14T09:00:00.000Z",
    sequence: 1,
    data: {},
  },
  {
    event_id: "event_2",
    type: "ai.input.processed",
    request_id: "req_test",
    occurred_at: "2026-07-14T09:00:00.500Z",
    sequence: 2,
    data: {},
  },
  {
    event_id: "event_3",
    type: "ai.agent.plan.created",
    request_id: "req_test",
    occurred_at: "2026-07-14T09:00:00.750Z",
    sequence: 3,
    data: { action: "answer", synthetic: false },
  },
  {
    event_id: "event_4",
    type: "ai.output.delta",
    request_id: "req_test",
    occurred_at: "2026-07-14T09:00:01.000Z",
    sequence: 4,
    data: { delta: "你好" },
  },
  {
    event_id: "event_5",
    type: "ai.output.completed",
    request_id: "req_test",
    occurred_at: "2026-07-14T09:00:02.000Z",
    sequence: 5,
    data: { content: "你好" },
  },
];

const diagnostics: RunDiagnosticTrace[] = [
  {
    id: "trace_prompt",
    type: "model.request",
    sequence: 1,
    occurred_at: "2026-07-14T09:00:00.700Z",
    data: {
      phase: "planner",
      llm: { provider: "openai", model: "gpt-test" },
      message_count: 1,
      tool_names: [],
      request_snapshot: {
        format: "openai-compatible.chat-completions.v1",
        messages: [{ role: "system", content: "Choose the next action" }],
        tools: [],
      },
    },
  },
  {
    id: "trace_tool_call",
    type: "tool.call",
    sequence: 2,
    occurred_at: "2026-07-14T09:00:01.200Z",
    data: {
      tool_call_id: "call_1",
      name: "capability_execute",
      argument_count: 1,
    },
  },
  {
    id: "trace_tool_result",
    type: "tool.result",
    sequence: 3,
    occurred_at: "2026-07-14T09:00:01.500Z",
    data: {
      tool_call_id: "call_1",
      name: "capability_execute",
      status: "ok",
      code: "",
    },
  },
];

describe("run detail model", () => {
  it("uses deltas once instead of duplicating the terminal output content", () => {
    expect(getRunOutput(events)).toBe("你好");
  });

  it("falls back to the completed output when stream chunks are unavailable", () => {
    expect(getRunOutput(events.slice(0, 1).concat(events[4]))).toBe("你好");
  });

  it("derives visible metrics only from Run and event contract fields", () => {
    expect(getRunMetrics(run, events)).toEqual([
      { label: "事件数", value: "5" },
      { label: "输出事件", value: "2" },
      { label: "最后序号", value: "5" },
      { label: "执行耗时", value: "2.5s" },
    ]);
  });

  it("creates a semantic graph and omits token-level stream fragments", () => {
    const graph = createRunEventGraph(run, events, "event_5");

    expect(graph.nodes).toHaveLength(5);
    expect(graph.nodes.map((node) => node.data.label)).toEqual([
      "入口请求",
      "用户提示词",
      "执行规划",
      "模型输出",
      "运行状态",
    ]);
    expect(graph.nodes.find((node) => node.data.label === "模型输出")).toMatchObject({
      selected: true,
      data: { detail: "你好", eventId: "event_5", state: "生成中" },
    });
    expect(graph.nodes.some((node) => node.data.eventType === "ai.output.delta")).toBe(false);
    expect(graph.edges).toHaveLength(4);
  });

  it("uses only post-reset deltas when no completed output is available", () => {
    const partialEvents = events.slice(0, 3).concat([
      { ...events[3], data: { delta: "旧输出" } },
      { ...events[3], event_id: "event_reset", type: "ai.output.reset", sequence: 5, data: {} },
      { ...events[3], event_id: "event_current", sequence: 6, data: { delta: "当前输出" } },
    ]);

    expect(getRunOutput(partialEvents)).toBe("当前输出");
  });

  it("puts model prompts and Skill/MCP tool execution into the runtime graph", () => {
    const graph = createRunTraceGraph(run, events, diagnostics, undefined);

    expect(graph.nodes.map((node) => node.data.label)).toContain("模型请求");
    expect(graph.nodes.map((node) => node.data.label)).toContain("执行 Skill / MCP");
    expect(graph.nodes.map((node) => node.data.label)).toContain("执行 Skill / MCP 结果");
    expect(
      graph.nodes.find((node) => node.data.traceId === "trace_prompt")?.data.diagnosticTrace,
    ).toEqual(diagnostics[0]);
  });
});
