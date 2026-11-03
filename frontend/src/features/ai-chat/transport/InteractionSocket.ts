import type { ImEnvelope } from "@/shared/api/generated/im";
import { newRandomId } from "@/shared/randomId";

type SharedOptions = {
  afterSequence: number;
  onEvent: (event: ImEnvelope) => void;
  onState: (state: "connected" | "connecting" | "disconnected") => void;
};

type ChannelSocketOptions = SharedOptions & {
  channelKey: string;
  admin?: never;
  interactionId?: string;
};

type AdminSocketOptions = SharedOptions & {
  admin: true;
  interactionId: string;
  channelKey?: never;
};

type SocketOptions = ChannelSocketOptions | AdminSocketOptions;

export type PendingActionReference = {
  action_id: string;
  action_hash: string;
  version: string;
};

export class InteractionSocket {
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private stopped = false;
  private sequence: number;
  private interactionId: string | undefined;

  constructor(private readonly options: SocketOptions) {
    this.sequence = options.afterSequence;
    this.interactionId = options.interactionId;
  }

  connect(): void {
    this.stopped = false;
    this.options.onState("connecting");
    this.socket = new WebSocket(this.url(), this.options.admin ? undefined : "parrot.im.v1");
    this.socket.onmessage = (message) => this.receive(message.data);
    this.socket.onclose = () => this.reconnect();
    this.socket.onerror = () => this.socket?.close();
  }

  close(): void {
    this.stopped = true;
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer);
    this.socket?.close(1000, "client closed");
    this.socket = null;
  }

  create(text: string): boolean {
    return this.sendCommand("interaction.create", { text });
  }

  cancel(): boolean {
    return this.sendCommand("interaction.cancel", {});
  }

  steer(message: string): boolean {
    return this.sendCommand("interaction.steer", { message });
  }

  resolveAction(decision: "approve" | "reject", action: PendingActionReference): boolean {
    return this.sendCommand("interaction." + decision, action);
  }

  private url(): string {
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    const path = this.options.admin
      ? "/api/v1/im/admin/ws?protocol=parrot.im.v1"
      : `/api/v1/im/ws/${encodeURIComponent(this.options.channelKey)}`;
    return `${scheme}//${window.location.host}${path}`;
  }

  private receive(raw: unknown): void {
    if (typeof raw !== "string") return;
    let event: ImEnvelope;
    try {
      event = JSON.parse(raw) as ImEnvelope;
    } catch {
      this.socket?.close(1007, "invalid event payload");
      return;
    }
    if (event.type === "connection.ready") {
      this.options.onState("connected");
      if (this.interactionId) this.sendSubscribe();
      return;
    }
    if (event.type === "interaction.accepted" && event.interaction_id) {
      this.interactionId = event.interaction_id;
      this.sequence = 0;
    }
    if (event.sequence !== null) this.sequence = Math.max(this.sequence, event.sequence);
    this.options.onEvent(event);
  }

  private sendSubscribe(): void {
    if (!this.interactionId) return;
    this.send("interaction.subscribe", {}, this.interactionId);
  }

  private sendCommand(type: string, data: Record<string, unknown>): boolean {
    if (type !== "interaction.create" && !this.interactionId) return false;
    return this.send(type, data, type === "interaction.create" ? undefined : this.interactionId);
  }

  private send(type: string, data: Record<string, unknown>, interactionId?: string): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    const id = newRandomId();
    this.socket.send(
      JSON.stringify({
        version: "1",
        type,
        message_id: `msg_web_${id}`,
        request_id: `req_web_${id}`,
        interaction_id: interactionId ?? null,
        sequence: this.sequence,
        occurred_at: new Date().toISOString(),
        data,
      } satisfies ImEnvelope),
    );
    return true;
  }

  private reconnect(): void {
    this.socket = null;
    this.options.onState("disconnected");
    if (this.stopped) return;
    this.reconnectTimer = window.setTimeout(() => this.connect(), 800);
  }
}
