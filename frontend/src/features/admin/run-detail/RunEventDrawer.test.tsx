import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RunDiagnosticTrace, RunEvent } from "@/shared/api/types";

import { RunEventDrawer } from "./RunEventDrawer";

const event: RunEvent = {
  event_id: "event_42",
  type: "ai.output.completed",
  request_id: "req_42",
  occurred_at: "2026-07-14T09:00:02.000Z",
  sequence: 42,
  data: { content: "任务已完成" },
};

const promptTrace: RunDiagnosticTrace = {
  id: "trace_prompt",
  type: "model.request",
  sequence: 1,
  occurred_at: "2026-07-14T09:00:01.000Z",
  data: {
    phase: "agent_loop",
    attempt: 1,
    llm: { provider: "openai", model: "gpt-test" },
    message_count: 1,
    tool_names: ["knowledge_search"],
    request_snapshot: {
      format: "openai-compatible.chat-completions.v1",
      messages: [{ role: "system", content: "You are a helpful agent." }],
      tools: [
        {
          type: "function",
          function: { name: "knowledge_search", parameters: { type: "object" } },
        },
      ],
    },
  },
};

afterEach(cleanup);

describe("RunEventDrawer", () => {
  it("renders the selected event contract fields and delegates closing", () => {
    const onClose = vi.fn();
    render(<RunEventDrawer event={event} open onClose={onClose} />);

    expect(screen.getByRole("dialog", { name: "事件详情" })).toBeInTheDocument();
    expect(screen.getByText("ai.output.completed")).toBeInTheDocument();
    expect(screen.getByText("event_42")).toBeInTheDocument();
    expect(screen.getByText("req_42")).toBeInTheDocument();
    expect(screen.getByLabelText("事件载荷")).toHaveTextContent('"content": "任务已完成"');

    fireEvent.click(screen.getByRole("button", { name: "关闭事件详情" }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("shows the submitted user prompt for the semantic input node", () => {
    render(
      <RunEventDrawer
        event={{ ...event, type: "ai.input.processed" }}
        node={{
          detail: "请总结这段内容",
          eventId: event.event_id,
          eventType: "ai.input.processed",
          icon: "Message",
          label: "用户提示词",
          modelInput: {
            entryType: "text",
            inputType: "text",
            userPrompt: "请总结这段内容",
          },
          occurredAt: event.occurred_at,
          sequence: event.sequence,
          state: "已送入 Agent Loop",
          tone: "warning",
        }}
        open
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole("dialog", { name: "用户提示词详情" })).toBeInTheDocument();
    expect(screen.getByLabelText("提交给模型的用户输入")).toHaveTextContent("请总结这段内容");
    expect(screen.queryByText("模型上下文安全边界")).not.toBeInTheDocument();
  });

  it("shows the provider-ready request snapshot for a diagnostic canvas node", () => {
    render(
      <RunEventDrawer
        node={{
          detail: "1 条 messages · 1 个工具定义",
          diagnosticTrace: promptTrace,
          eventType: promptTrace.type,
          icon: "RobotOne",
          label: "模型请求",
          occurredAt: promptTrace.occurred_at,
          sequence: promptTrace.sequence,
          state: "openai / gpt-test",
          tone: "warning",
          traceId: promptTrace.id,
        }}
        open
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole("dialog", { name: "模型提示词详情" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("system"));
    expect(screen.getByLabelText("内容")).toHaveTextContent("You are a helpful agent.");
    expect(screen.getByText("实际发送给模型的工具定义")).toBeInTheDocument();
  });

  it("labels historical metadata-only records without inventing a prompt snapshot", () => {
    render(
      <RunEventDrawer
        node={{
          detail: "2 条 messages · 1 个工具定义",
          diagnosticTrace: {
            ...promptTrace,
            data: {
              phase: "agent_loop",
              attempt: 1,
              llm: { provider: "openai", model: "gpt-test" },
              message_count: 2,
              message_roles: ["system", "user"],
              tool_names: ["knowledge_search"],
            },
          },
          eventType: promptTrace.type,
          icon: "RobotOne",
          label: "模型请求",
          occurredAt: promptTrace.occurred_at,
          sequence: promptTrace.sequence,
          state: "openai / gpt-test",
          tone: "warning",
          traceId: promptTrace.id,
        }}
        open
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("2 条")).toBeInTheDocument();
    expect(screen.getByText("该运行未保存完整请求快照")).toBeInTheDocument();
  });
});
