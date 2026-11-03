import { useCallback, useEffect, useRef, useState } from "react";
import { App, Spin } from "antd";
import { useParams } from "react-router-dom";

import { ChatComposer } from "@/features/ai-chat/ChatComposer";
import { ChatKnowledgeSources } from "@/features/ai-chat/ChatKnowledgeSources";
import { ChatNotices, type OutputState } from "@/features/ai-chat/ChatNotices";
import {
  appendAssistantDelta,
  appendThinkingDelta,
  completeAssistant,
  completeStreamingMessages,
  completeThinking,
  interactionOutputId,
  outputCitations,
  outputContent,
  outputId,
  outputMedia,
  outputRuntimeStatus,
  pendingActionFrom,
  resetAssistantOutput,
  socketErrorMessage,
  thinkingContent,
  type ChatMessageModel,
} from "@/features/ai-chat/chatMessages";
import { InteractionSocket } from "@/features/ai-chat/transport/InteractionSocket";
import type { PendingActionReference } from "@/features/ai-chat/transport/InteractionSocket";
import type { ImEnvelope } from "@/shared/api/generated/im";
import { AppIcon } from "@/shared/icons";
import { newRandomId } from "@/shared/randomId";
import { MarkdownPreview } from "@/shared/ui";

import "./chat.css";

type ConnectionState = "connected" | "connecting" | "disconnected";

export function ChatPage() {
  const { channelKey = "" } = useParams();
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessageModel[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("disconnected");
  const [submitting, setSubmitting] = useState(false);
  const [canSteer, setCanSteer] = useState(false);
  const [outputState, setOutputState] = useState<OutputState>(null);
  const [pendingAction, setPendingAction] = useState<PendingActionReference | null>(null);
  const [resolvingAction, setResolvingAction] = useState(false);
  const { message } = App.useApp();
  const socketRef = useRef<InteractionSocket | null>(null);
  const seenEvents = useRef(new Set<string>());
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const receive = useCallback(
    (event: ImEnvelope) => {
      if (seenEvents.current.has(event.message_id)) return;
      seenEvents.current.add(event.message_id);
      if (event.type === "ai.thinking.delta") {
        const delta = typeof event.data.delta === "string" ? event.data.delta : "";
        setMessages((current) =>
          appendThinkingDelta(current, interactionOutputId(event), delta),
        );
      } else if (event.type === "ai.thinking.completed") {
        setMessages((current) =>
          completeThinking(current, interactionOutputId(event), thinkingContent(event)),
        );
      } else if (event.type === "ai.output.delta") {
        const delta = typeof event.data.delta === "string" ? event.data.delta : "";
        setMessages((current) => appendAssistantDelta(current, outputId(event), delta));
      } else if (event.type === "ai.output.reset") {
        setMessages((current) => resetAssistantOutput(current, outputId(event)));
      } else if (event.type === "ai.output.completed") {
        const runtimeStatus = outputRuntimeStatus(event);
        setPendingAction(runtimeStatus === "waiting_user_action" ? pendingActionFrom(event) : null);
        setMessages((current) =>
          completeAssistant(current, outputId(event), outputContent(event), {
            interactionId: event.interaction_id,
            citations: outputCitations(event),
            media: outputMedia(event),
          }),
        );
        setCanSteer(runtimeStatus === "waiting_user_input");
        setOutputState(runtimeStatus);
        setSubmitting(false);
        setResolvingAction(false);
      } else if (event.type === "ai.output.cancelled") {
        setMessages(completeStreamingMessages);
        setCanSteer(false);
        setOutputState(null);
        setPendingAction(null);
        setResolvingAction(false);
        setSubmitting(false);
      } else if (event.type === "ai.output.failed") {
        setMessages((current) =>
          completeAssistant(current, outputId(event), socketErrorMessage(event)),
        );
        setCanSteer(false);
        setOutputState("failed");
        setPendingAction(null);
        setResolvingAction(false);
        setSubmitting(false);
      } else if (event.type === "error") {
        void message.error(socketErrorMessage(event));
        setCanSteer(false);
        setOutputState(null);
        setPendingAction(null);
        setResolvingAction(false);
        setSubmitting(false);
      }
    },
    [message],
  );

  useEffect(() => {
    if (!channelKey) return;
    const socket = new InteractionSocket({
      channelKey,
      afterSequence: 0,
      onEvent: receive,
      onState: setConnection,
    });
    socketRef.current = socket;
    socket.connect();
    return () => {
      socket.close();
      if (socketRef.current === socket) socketRef.current = null;
    };
  }, [channelKey, receive]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, submitting]);

  const submit = useCallback(() => {
    const text = draft.trim();
    if (!text || submitting) return;
    if (canSteer && !socketRef.current?.steer(text)) {
      void message.error("实时连接尚未恢复，请稍后重试。");
      return;
    }
    if (!canSteer && !socketRef.current?.create(text)) {
      void message.error("实时连接尚未建立或正在恢复，请稍后重试。");
      return;
    }
    seenEvents.current.clear();
    setSubmitting(true);
    setDraft("");
    setMessages((current) => [...current, { id: newRandomId(), role: "user", content: text }]);
    if (canSteer) {
      setCanSteer(false);
      setOutputState(null);
      return;
    }
    setOutputState(null);
  }, [canSteer, draft, message, submitting]);

  const resolveAction = useCallback(
    (decision: "approve" | "reject") => {
      if (!pendingAction || resolvingAction) return;
      if (!socketRef.current?.resolveAction(decision, pendingAction)) {
        void message.error("实时连接尚未恢复，请稍后重试。");
        return;
      }
      setResolvingAction(true);
      setSubmitting(true);
      setPendingAction(null);
      setOutputState(null);
    },
    [message, pendingAction, resolvingAction],
  );

  return (
    <main className="chat-page">
      <header className="chat-header">
        <div className="chat-identity">
          <span className="chat-avatar" aria-hidden="true">
            <AppIcon name="RobotOne" size="xl" />
          </span>
          <div>
            <span className="chat-kicker">PARROT AI</span>
            <h1>Parrot Agent</h1>
            <p>实时智能体对话</p>
          </div>
        </div>
        <ConnectionIndicator state={connection} />
      </header>
      <section className="chat-messages" aria-live="polite">
        {messages.length === 0 ? (
          <div className="chat-welcome">
            <AppIcon name="Message" size="2xl" />
            <h2>开始一段对话</h2>
            <p>输出将通过安全 WebSocket 实时送达，并支持断线恢复。</p>
          </div>
        ) : (
          messages.map((item) => <ChatBubble key={item.id} message={item} />)
        )}
        {submitting && !messages.some((item) => item.streaming) ? <Spin size="small" /> : null}
        <div ref={messagesEndRef} />
      </section>
      <ChatNotices
        outputState={outputState}
        pendingAction={pendingAction}
        resolvingAction={resolvingAction}
        onResolveAction={resolveAction}
      />
      <ChatComposer
        canSteer={canSteer}
        draft={draft}
        onCancel={() => socketRef.current?.cancel()}
        onChange={setDraft}
        onSubmit={() => void submit()}
        submitting={submitting}
      />
    </main>
  );
}

function ChatBubble({ message }: { message: ChatMessageModel }) {
  const showSpinner = message.streaming && !message.content && !message.thinking;
  return (
    <article className={`chat-message chat-message-${message.role}`}>
      <div className="chat-bubble">
        {message.thinking ? (
          <details className="chat-thinking" open={!message.thinkingDone || !message.content}>
            <summary>{message.thinkingDone ? "思考过程" : "思考中…"}</summary>
            <pre>{message.thinking}</pre>
          </details>
        ) : null}
        {message.content ? (
          message.role === "assistant" ? (
            <MarkdownPreview
              className="chat-markdown"
              highlightCode={!message.streaming}
              value={message.content}
            />
          ) : (
            message.content
          )
        ) : showSpinner ? (
          <Spin size="small" />
        ) : null}
        {message.role === "assistant" && !message.streaming ? (
          <ChatKnowledgeSources
            citations={message.citations ?? []}
            interactionId={message.interactionId ?? null}
            media={message.media ?? []}
          />
        ) : null}
      </div>
      {message.streaming && message.content ? (
        <span className="streaming-cursor" aria-label="正在生成" />
      ) : null}
    </article>
  );
}

function ConnectionIndicator({ state }: { state: ConnectionState }) {
  const labels = { connected: "实时连接", connecting: "连接中", disconnected: "未连接" };
  return (
    <div className={`connection-indicator connection-indicator-${state}`} role="status">
      <span className="connection-indicator-dot" aria-hidden="true" />
      <span>{labels[state]}</span>
    </div>
  );
}
