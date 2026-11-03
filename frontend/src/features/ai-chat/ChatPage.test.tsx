import { StrictMode } from "react";
import { App as AntdApp } from "antd";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPage } from "@/features/ai-chat/ChatPage";

const nativeScrollIntoView = Object.getOwnPropertyDescriptor(
  HTMLElement.prototype,
  "scrollIntoView",
);

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  if (nativeScrollIntoView) {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", nativeScrollIntoView);
  } else {
    Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
  }
});

beforeEach(() => {
  vi.stubGlobal("WebSocket", TestWebSocket);
});

describe("ChatPage", () => {
  it("submits messages when crypto.randomUUID is unavailable on an HTTP origin", () => {
    const sockets: TestWebSocket[] = [];
    vi.stubGlobal(
      "WebSocket",
      class extends TestWebSocket {
        constructor(...args: ConstructorParameters<typeof TestWebSocket>) {
          super(...args);
          sockets.push(this);
        }
      },
    );
    const originalDescriptor = Object.getOwnPropertyDescriptor(crypto, "randomUUID");
    Object.defineProperty(crypto, "randomUUID", { configurable: true, value: undefined });

    try {
      render(
        <AntdApp>
          <MemoryRouter initialEntries={["/im/websocket/channel_http"]}>
            <Routes>
              <Route path="im/websocket/:channelKey" element={<ChatPage />} />
            </Routes>
          </MemoryRouter>
        </AntdApp>,
      );
      fireEvent.change(screen.getByPlaceholderText("输入消息，Enter 发送，Shift+Enter 换行"), {
        target: { value: "HTTP 环境消息" },
      });

      fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

      expect(sockets[0].sent).toHaveLength(1);
      expect(screen.getByText("HTTP 环境消息")).toBeInTheDocument();
    } finally {
      if (originalDescriptor) {
        Object.defineProperty(crypto, "randomUUID", originalDescriptor);
      } else {
        Reflect.deleteProperty(crypto, "randomUUID");
      }
    }
  });

  it("uses a compact status indicator instead of a tag while connecting", () => {
    render(
      <AntdApp>
        <MemoryRouter initialEntries={["/im/websocket/channel_test"]}>
          <Routes>
            <Route path="im/websocket/:channelKey" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </AntdApp>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("连接中");
    expect(document.querySelector(".connection-indicator-connecting")).toBeInTheDocument();
    expect(document.querySelector(".connection-indicator .ant-tag")).not.toBeInTheDocument();
  });

  it("does not expose scrollIntoView's return value as an effect cleanup", () => {
    const scrollIntoView = vi.fn(() => ({ unexpected: "return value" }));
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });

    const { unmount } = render(
      <AntdApp>
        <StrictMode>
          <MemoryRouter initialEntries={["/im/websocket/channel_test"]}>
            <Routes>
              <Route path="im/websocket/:channelKey" element={<ChatPage />} />
            </Routes>
          </MemoryRouter>
        </StrictMode>
      </AntdApp>,
    );

    expect(() => unmount()).not.toThrow();
    expect(scrollIntoView).toHaveBeenCalled();
  });

  it("renders streamed assistant output as Markdown while preserving user input as plain text", () => {
    const sockets: TestWebSocket[] = [];
    vi.stubGlobal(
      "WebSocket",
      class extends TestWebSocket {
        constructor(...args: ConstructorParameters<typeof TestWebSocket>) {
          super(...args);
          sockets.push(this);
        }
      },
    );
    render(
      <AntdApp>
        <MemoryRouter initialEntries={["/im/websocket/channel_test"]}>
          <Routes>
            <Route path="im/websocket/:channelKey" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </AntdApp>,
    );

    fireEvent.change(screen.getByPlaceholderText("输入消息，Enter 发送，Shift+Enter 换行"), {
      target: { value: "# 用户原始输入" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    const socket = sockets[0];
    if (!socket) throw new Error("WebSocket was not created");
    act(() => {
      socket.emit({
        type: "ai.output.delta",
        message_id: "msg_assistant_markdown",
        interaction_id: "interaction_1",
        sequence: 1,
        data: { output_id: "output_1", delta: "## Markdown 输出\n\n- 已格式化" },
      });
    });

    expect(screen.getByRole("heading", { name: "Markdown 输出" })).toBeInTheDocument();
    expect(screen.getByRole("list")).toHaveTextContent("已格式化");
    expect(screen.getByText("# 用户原始输入")).toBeInTheDocument();
  });

  it("replaces partial output with the terminal content after a reset and re-render", () => {
    const sockets: TestWebSocket[] = [];
    vi.stubGlobal(
      "WebSocket",
      class extends TestWebSocket {
        constructor(...args: ConstructorParameters<typeof TestWebSocket>) {
          super(...args);
          sockets.push(this);
        }
      },
    );
    render(
      <AntdApp>
        <MemoryRouter initialEntries={["/im/websocket/channel_test"]}>
          <Routes>
            <Route path="im/websocket/:channelKey" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </AntdApp>,
    );
    const socket = sockets[0];
    if (!socket) throw new Error("WebSocket was not created");

    act(() => {
      socket.emit(outputEvent("ai.output.delta", "event_delta_first", { delta: "旧草稿" }));
      socket.emit(outputEvent("ai.output.reset", "event_reset", {}));
      socket.emit(outputEvent("ai.output.delta", "event_delta_second", { delta: "不完整答案" }));
      socket.emit(
        outputEvent("ai.output.completed", "event_completed", { content: "权威最终答案" }),
      );
    });

    expect(screen.queryByText("旧草稿")).not.toBeInTheDocument();
    expect(screen.queryByText("不完整答案")).not.toBeInTheDocument();
    expect(screen.getByText("权威最终答案")).toBeInTheDocument();
  });

  it("shows the WebSocket error message in a toast instead of the chat page", async () => {
    const sockets: TestWebSocket[] = [];
    vi.stubGlobal(
      "WebSocket",
      class extends TestWebSocket {
        constructor(...args: ConstructorParameters<typeof TestWebSocket>) {
          super(...args);
          sockets.push(this);
        }
      },
    );
    render(
      <AntdApp>
        <MemoryRouter initialEntries={["/im/websocket/channel_test"]}>
          <Routes>
            <Route path="im/websocket/:channelKey" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </AntdApp>,
    );
    const socket = sockets[0];
    if (!socket) throw new Error("WebSocket was not created");

    act(() => {
      socket.emit({
        version: "1",
        type: "error",
        message_id: "msg_error_1",
        request_id: "req_web_error_1",
        interaction_id: null,
        sequence: 0,
        occurred_at: null,
        data: {
          code: "SKILL_BUILD_REQUIRED",
          message: "可执行 Skill 的草稿尚未完成当前构建，请先点击“构建草稿”，构建成功后再发布。",
        },
      });
    });

    expect(
      await screen.findByText(
        "可执行 Skill 的草稿尚未完成当前构建，请先点击“构建草稿”，构建成功后再发布。",
      ),
    ).toBeInTheDocument();
    expect(document.querySelector(".chat-notices .ant-alert-error")).not.toBeInTheDocument();
  });

  it("keeps an LLM runtime failure visible in the conversation", () => {
    const sockets: TestWebSocket[] = [];
    vi.stubGlobal(
      "WebSocket",
      class extends TestWebSocket {
        constructor(...args: ConstructorParameters<typeof TestWebSocket>) {
          super(...args);
          sockets.push(this);
        }
      },
    );
    render(
      <AntdApp>
        <MemoryRouter initialEntries={["/im/websocket/channel_test"]}>
          <Routes>
            <Route path="im/websocket/:channelKey" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </AntdApp>,
    );
    const socket = sockets[0];
    if (!socket) throw new Error("WebSocket was not created");

    act(() => {
      socket.emit(
        outputEvent("ai.output.failed", "event_failed", {
          code: "AI_PROVIDER_UNAVAILABLE",
          message: "智能体运行服务暂时不可用，请稍后重试。",
        }),
      );
    });

    expect(screen.getByText("智能体运行服务暂时不可用，请稍后重试。")).toBeInTheDocument();
    expect(screen.getByText("本次运行失败")).toBeInTheDocument();
    expect(document.querySelector(".chat-notices .ant-alert-error")).toBeInTheDocument();
    expect(screen.queryByLabelText("正在生成")).not.toBeInTheDocument();
  });

  it("sends a structured approval without exposing editable tool parameters", () => {
    const sockets: TestWebSocket[] = [];
    vi.stubGlobal(
      "WebSocket",
      class extends TestWebSocket {
        constructor(...args: ConstructorParameters<typeof TestWebSocket>) {
          super(...args);
          sockets.push(this);
        }
      },
    );
    render(
      <AntdApp>
        <MemoryRouter initialEntries={["/im/websocket/channel_test"]}>
          <Routes>
            <Route path="im/websocket/:channelKey" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </AntdApp>,
    );
    const socket = sockets[0];
    if (!socket) throw new Error("WebSocket was not created");

    act(() => {
      socket.emit({
        version: "1",
        type: "interaction.accepted",
        message_id: "accepted_1",
        request_id: "request_1",
        interaction_id: "interaction_1",
        sequence: 0,
        occurred_at: null,
        data: { status: "accepted" },
      });
      socket.emit({
        version: "1",
        type: "ai.output.completed",
        message_id: "waiting_1",
        request_id: "request_1",
        interaction_id: "interaction_1",
        sequence: 1,
        occurred_at: null,
        data: {
          output_id: "output_1",
          content: "此操作需要你的明确确认。",
          runtime_status: "waiting_user_action",
          action: {
            action_id: "pending_1",
            action_hash: "sha256:action",
            version: "v1",
            choices: ["approve", "reject"],
          },
        },
      });
    });

    expect(screen.queryByText("create_ticket")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /批\s*准/ }));
    const sent = JSON.parse(socket.sent[socket.sent.length - 1] ?? "{}") as Record<string, unknown>;
    expect(sent).toMatchObject({
      type: "interaction.approve",
      interaction_id: "interaction_1",
      data: {
        action_id: "pending_1",
        action_hash: "sha256:action",
        version: "v1",
      },
    });
  });

  it("keeps showing progress after sending a waiting-input follow-up", () => {
    const sockets: TestWebSocket[] = [];
    vi.stubGlobal(
      "WebSocket",
      class extends TestWebSocket {
        constructor(...args: ConstructorParameters<typeof TestWebSocket>) {
          super(...args);
          sockets.push(this);
        }
      },
    );
    render(
      <AntdApp>
        <MemoryRouter initialEntries={["/im/websocket/channel_test"]}>
          <Routes>
            <Route path="im/websocket/:channelKey" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </AntdApp>,
    );
    const socket = sockets[0];
    if (!socket) throw new Error("WebSocket was not created");

    act(() => {
      socket.emit({
        version: "1",
        type: "interaction.accepted",
        message_id: "accepted_steer",
        request_id: "request_steer",
        interaction_id: "interaction_steer",
        sequence: 0,
        occurred_at: null,
        data: { status: "accepted" },
      });
      socket.emit({
        version: "1",
        type: "ai.output.completed",
        message_id: "waiting_steer",
        request_id: "request_steer",
        interaction_id: "interaction_steer",
        sequence: 1,
        occurred_at: null,
        data: {
          output_id: "output_steer",
          content: "请补充城市。",
          runtime_status: "waiting_user_input",
        },
      });
    });

    fireEvent.change(screen.getByPlaceholderText("补充信息后按 Enter 继续"), {
      target: { value: "上海" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    const sent = JSON.parse(socket.sent[socket.sent.length - 1] ?? "{}") as Record<string, unknown>;
    expect(sent).toMatchObject({
      type: "interaction.steer",
      interaction_id: "interaction_steer",
      data: { message: "上海" },
    });
    expect(screen.getByRole("button", { name: "停止生成" })).toBeInTheDocument();
  });
});

class TestWebSocket {
  static readonly OPEN = 1;
  readyState = TestWebSocket.OPEN;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readonly sent: string[] = [];

  constructor(...args: unknown[]) {
    void args;
  }

  close(): void {
    this.readyState = 3;
  }

  send(value: string): void {
    this.sent.push(value);
  }

  emit(event: Record<string, unknown>): void {
    this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent<string>);
  }
}

function outputEvent(
  type: "ai.output.delta" | "ai.output.reset" | "ai.output.completed" | "ai.output.failed",
  messageId: string,
  data: Record<string, string>,
) {
  return {
    version: "1",
    type,
    message_id: messageId,
    request_id: "request_test",
    interaction_id: "interaction_test",
    sequence: 1,
    occurred_at: null,
    data: { output_id: "output_test", ...data },
  };
}
