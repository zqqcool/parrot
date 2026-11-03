import type { ImEnvelope } from "@/shared/api/generated/im";

import type { OutputState } from "@/features/ai-chat/ChatNotices";
import type { PendingActionReference } from "@/features/ai-chat/transport/InteractionSocket";

export type ChatOutputCitation = {
  citation_id: string;
  title: string;
  anchor: string;
  slide_no: number | null;
};

export type ChatOutputMedia = {
  citation_id: string;
  asset_id: string;
  kind: string;
  role: string;
  alt: string | null;
};

export type ChatMessageModel = {
  id: string;
  role: "assistant" | "user";
  content: string;
  thinking?: string;
  thinkingDone?: boolean;
  streaming?: boolean;
  interactionId?: string | null;
  citations?: ChatOutputCitation[];
  media?: ChatOutputMedia[];
};

export function appendThinkingDelta(
  messages: ChatMessageModel[],
  id: string,
  delta: string,
): ChatMessageModel[] {
  const index = messages.findIndex((message) => message.id === id);
  if (index < 0) {
    return [...messages, { id, role: "assistant", content: "", thinking: delta, streaming: true }];
  }
  return messages.map((message, position) =>
    position === index
      ? {
          ...message,
          thinking: `${message.thinking ?? ""}${delta}`,
          thinkingDone: false,
          streaming: true,
        }
      : message,
  );
}

export function completeThinking(
  messages: ChatMessageModel[],
  id: string,
  content: string,
): ChatMessageModel[] {
  return messages.map((message) =>
    message.id === id
      ? {
          ...message,
          thinking: message.thinking || content,
          thinkingDone: true,
        }
      : message,
  );
}

export function appendAssistantDelta(
  messages: ChatMessageModel[],
  id: string,
  delta: string,
): ChatMessageModel[] {
  const index = messages.findIndex((message) => message.id === id);
  if (index < 0) return [...messages, { id, role: "assistant", content: delta, streaming: true }];
  return messages.map((message, position) =>
    position === index
      ? { ...message, content: message.content + delta, streaming: true }
      : message,
  );
}

export function resetAssistantOutput(
  messages: ChatMessageModel[],
  id: string,
): ChatMessageModel[] {
  return messages.map((message) =>
    message.id === id ? { ...message, content: "", streaming: true } : message,
  );
}

export function completeAssistant(
  messages: ChatMessageModel[],
  id: string,
  content: string,
  extras: {
    interactionId?: string | null;
    citations?: ChatOutputCitation[];
    media?: ChatOutputMedia[];
  } = {},
): ChatMessageModel[] {
  const patch = {
    content: content || undefined,
    streaming: false as const,
    interactionId: extras.interactionId,
    citations: extras.citations,
    media: extras.media,
  };
  if (!messages.some((message) => message.id === id)) {
    return content
      ? [
          {
            id,
            role: "assistant",
            content,
            interactionId: extras.interactionId ?? null,
            citations: extras.citations ?? [],
            media: extras.media ?? [],
          },
        ]
      : messages;
  }
  return messages.map((message) =>
    message.id === id
      ? {
          ...message,
          content: patch.content || message.content,
          streaming: false,
          interactionId: extras.interactionId ?? message.interactionId ?? null,
          citations: extras.citations ?? message.citations ?? [],
          media: extras.media ?? message.media ?? [],
        }
      : message,
  );
}

export function completeStreamingMessages(messages: ChatMessageModel[]): ChatMessageModel[] {
  return messages.map((message) =>
    message.streaming ? { ...message, streaming: false } : message,
  );
}

export function outputId(event: ImEnvelope): string {
  return typeof event.data.output_id === "string"
    ? event.data.output_id
    : interactionOutputId(event);
}

export function interactionOutputId(event: ImEnvelope): string {
  return `output_${event.interaction_id ?? event.message_id}`;
}

export function thinkingContent(event: ImEnvelope): string {
  return typeof event.data.content === "string" ? event.data.content : "";
}

export function outputContent(event: ImEnvelope): string {
  return typeof event.data.content === "string" ? event.data.content : "";
}

export function outputCitations(event: ImEnvelope): ChatOutputCitation[] {
  const rows = event.data.citations;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap((row) => {
    if (!row || typeof row !== "object") return [];
    const value = row as Record<string, unknown>;
    if (
      typeof value.citation_id !== "string" ||
      typeof value.title !== "string" ||
      typeof value.anchor !== "string"
    ) {
      return [];
    }
    return [
      {
        citation_id: value.citation_id,
        title: value.title,
        anchor: value.anchor,
        slide_no: typeof value.slide_no === "number" ? value.slide_no : null,
      },
    ];
  });
}

export function outputMedia(event: ImEnvelope): ChatOutputMedia[] {
  const rows = event.data.media;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap((row) => {
    if (!row || typeof row !== "object") return [];
    const value = row as Record<string, unknown>;
    if (
      typeof value.citation_id !== "string" ||
      typeof value.asset_id !== "string" ||
      typeof value.kind !== "string"
    ) {
      return [];
    }
    return [
      {
        citation_id: value.citation_id,
        asset_id: value.asset_id,
        kind: value.kind,
        role: typeof value.role === "string" ? value.role : "primary",
        alt: typeof value.alt === "string" ? value.alt : null,
      },
    ];
  });
}

export function socketErrorMessage(event: ImEnvelope) {
  return typeof event.data.message === "string" && event.data.message.trim()
    ? event.data.message
    : "实时交互失败，请稍后重试。";
}

export function outputRuntimeStatus(event: ImEnvelope): OutputState {
  if (
    event.data.runtime_status === "partial" ||
    event.data.runtime_status === "waiting_user_input" ||
    event.data.runtime_status === "waiting_user_action"
  ) {
    return event.data.runtime_status;
  }
  return null;
}

export function pendingActionFrom(event: ImEnvelope): PendingActionReference | null {
  const action = event.data.action;
  if (!action || typeof action !== "object") return null;
  const value = action as Record<string, unknown>;
  if (
    typeof value.action_id !== "string" ||
    typeof value.action_hash !== "string" ||
    typeof value.version !== "string"
  ) {
    return null;
  }
  return {
    action_id: value.action_id,
    action_hash: value.action_hash,
    version: value.version,
  };
}
