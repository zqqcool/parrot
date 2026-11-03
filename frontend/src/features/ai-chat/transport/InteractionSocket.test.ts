import { afterEach, describe, expect, it, vi } from "vitest";

import { InteractionSocket } from "@/features/ai-chat/transport/InteractionSocket";

class FakeWebSocket {
  static readonly OPEN = 1;
  readonly sent: string[] = [];
  readyState = FakeWebSocket.OPEN;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(
    readonly url: string,
    readonly protocols?: string | string[],
  ) {
    sockets.push(this);
  }

  send(value: string): void {
    this.sent.push(value);
  }

  close(): void {
    this.readyState = 3;
  }
}

const sockets: FakeWebSocket[] = [];

afterEach(() => {
  sockets.length = 0;
  vi.unstubAllGlobals();
});

describe("InteractionSocket", () => {
  it("sends commands when crypto.randomUUID is unavailable on an HTTP origin", () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const originalDescriptor = Object.getOwnPropertyDescriptor(crypto, "randomUUID");
    Object.defineProperty(crypto, "randomUUID", { configurable: true, value: undefined });
    const client = new InteractionSocket({
      channelKey: "channel_http",
      afterSequence: 0,
      onEvent: vi.fn(),
      onState: vi.fn(),
    });

    try {
      client.connect();

      expect(client.create("hello over HTTP")).toBe(true);
      const command = JSON.parse(sockets[0].sent[0]) as Record<string, unknown>;
      expect(command.message_id).toMatch(/^msg_web_[0-9a-f]{32}$/);
      expect(command.request_id).toMatch(/^req_web_[0-9a-f]{32}$/);
    } finally {
      if (originalDescriptor) {
        Object.defineProperty(crypto, "randomUUID", originalDescriptor);
      } else {
        Reflect.deleteProperty(crypto, "randomUUID");
      }
    }
  });

  it("creates and controls an interaction on the manually bound WebSocket channel", () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const client = new InteractionSocket({
      channelKey: "channel_test",
      afterSequence: 7,
      onEvent: vi.fn(),
      onState: vi.fn(),
    });

    client.connect();
    const socket = sockets[0];
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          version: "1",
          type: "connection.ready",
          message_id: "msg_ready",
          request_id: "req_ready",
          interaction_id: null,
          sequence: 0,
          occurred_at: null,
          data: {},
        }),
      }),
    );
    expect(socket.url).toContain("/api/v1/im/ws/channel_test");
    expect(socket.protocols).toBe("parrot.im.v1");
    expect(client.create("hello")).toBe(true);

    const create = JSON.parse(socket.sent[0]) as Record<string, unknown>;
    expect(create).toMatchObject({
      type: "interaction.create",
      interaction_id: null,
      sequence: 7,
    });
    socket.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          version: "1",
          type: "interaction.accepted",
          message_id: "msg_accepted",
          request_id: "req_accepted",
          interaction_id: "interaction_test",
          sequence: 0,
          occurred_at: null,
          data: { status: "accepted" },
        }),
      }),
    );
    client.cancel();

    const cancel = JSON.parse(socket.sent[1]) as Record<string, unknown>;
    expect(cancel).toMatchObject({
      type: "interaction.cancel",
      interaction_id: "interaction_test",
      sequence: 0,
    });
    expect(
      client.resolveAction("approve", {
        action_id: "pending_1",
        action_hash: "sha256:action",
        version: "v1",
      }),
    ).toBe(true);
    const approval = JSON.parse(socket.sent[2]) as Record<string, unknown>;
    expect(approval).toMatchObject({
      type: "interaction.approve",
      interaction_id: "interaction_test",
      data: {
        action_id: "pending_1",
        action_hash: "sha256:action",
        version: "v1",
      },
    });
  });

  it("uses the authenticated management socket for run progress", () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const client = new InteractionSocket({
      interactionId: "interaction_admin",
      afterSequence: 0,
      admin: true,
      onEvent: vi.fn(),
      onState: vi.fn(),
    });

    client.connect();

    expect(sockets[0].url).toContain("/api/v1/im/admin/ws?protocol=parrot.im.v1");
  });
});
