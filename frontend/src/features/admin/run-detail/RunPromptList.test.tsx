import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RunDiagnosticTrace } from "@/shared/api/types";

import { RunPromptList } from "./RunPromptList";

const prompts: RunDiagnosticTrace[] = [
  {
    id: "trace_intent",
    type: "model.request",
    sequence: 1,
    occurred_at: "2026-07-20T07:12:10.000Z",
    data: {
      phase: "knowledge_intent",
      llm: { provider: "deepseek", model: "deepseek-v4-flash" },
      message_count: 2,
      tool_names: [],
      request_snapshot: {
        format: "openai-compatible.chat-completions.v1",
        messages: [
          { role: "system", content: "Classify intent" },
          { role: "user", content: "亚朵酒店" },
        ],
        tools: [],
      },
    },
  },
  {
    id: "trace_loop",
    type: "model.request",
    sequence: 2,
    occurred_at: "2026-07-20T07:12:15.000Z",
    data: {
      phase: "agent_loop",
      llm: { provider: "deepseek", model: "deepseek-v4-flash" },
      message_count: 3,
      tool_names: ["knowledge_search"],
    },
  },
];

afterEach(cleanup);

describe("RunPromptList", () => {
  it("summarizes model calls and distinguishes snapshots from metadata-only traces", () => {
    render(<RunPromptList error={undefined} loading={false} traces={prompts} onSelect={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "模型调用记录" })).toBeInTheDocument();
    expect(screen.getByLabelText("模型调用概览")).toHaveTextContent("2 次调用");
    expect(screen.getByLabelText("模型调用概览")).toHaveTextContent("5 条消息");
    expect(screen.getByLabelText("模型调用概览")).toHaveTextContent("1 次携带工具");
    expect(screen.getByText("知识意图识别")).toBeInTheDocument();
    expect(screen.getByText("已保存请求快照")).toBeInTheDocument();
    expect(screen.getByText("仅元数据")).toBeInTheDocument();
  });

  it("opens the selected diagnostic record from its explicit action", () => {
    const onSelect = vi.fn();
    render(
      <RunPromptList error={undefined} loading={false} traces={prompts} onSelect={onSelect} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "查看请求快照：知识意图识别" }));

    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({
        traceId: "trace_intent",
        detail: "查看实际发送给模型的 messages 与工具定义",
        state: "请求快照",
      }),
    );
  });
});
