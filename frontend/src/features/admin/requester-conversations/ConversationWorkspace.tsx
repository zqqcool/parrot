import { Empty, List, Spin, Tag } from "antd";

import type { ConversationMessage, ConversationSummary } from "@/shared/api/types";
import { formatDateTime } from "@/shared/time";
import { MarkdownPreview } from "@/shared/ui";

import "./conversation-workspace.css";

type ConversationWorkspaceProps = {
  conversations: ConversationSummary[];
  conversationsLoading: boolean;
  messages: ConversationMessage[];
  messagesError: unknown;
  messagesLoading: boolean;
  selectedConversation: ConversationSummary | undefined;
  onSelectConversation: (conversation: ConversationSummary) => void;
  onViewRun: (interactionId: string) => void;
};

export function ConversationWorkspace({
  conversations,
  conversationsLoading,
  messages,
  messagesError,
  messagesLoading,
  selectedConversation,
  onSelectConversation,
  onViewRun,
}: ConversationWorkspaceProps) {
  const showConversationList =
    conversationsLoading || conversations.length !== 1 || !selectedConversation;

  return (
    <div
      className={`conversation-workspace ${showConversationList ? "" : "conversation-workspace--single"}`}
    >
      {showConversationList ? (
        <ConversationList
          conversations={conversations}
          loading={conversationsLoading}
          selected={selectedConversation}
          onSelect={onSelectConversation}
        />
      ) : null}
      <ConversationMessages
        messages={messages}
        error={messagesError}
        loading={messagesLoading}
        selected={selectedConversation}
        onViewRun={onViewRun}
      />
    </div>
  );
}

function ConversationList({
  conversations,
  loading,
  selected,
  onSelect,
}: {
  conversations: ConversationSummary[];
  loading: boolean;
  selected: ConversationSummary | undefined;
  onSelect: (conversation: ConversationSummary) => void;
}) {
  return (
    <aside className="conversation-workspace__list" aria-label="会话列表">
      {loading ? <Spin /> : null}
      {!loading && !conversations.length ? <Empty description="暂无可展示的对话" /> : null}
      <List
        dataSource={conversations}
        renderItem={(conversation) => (
          <List.Item className="conversation-list-item">
            <ConversationListButton
              conversation={conversation}
              selected={selected}
              onSelect={onSelect}
            />
          </List.Item>
        )}
      />
    </aside>
  );
}

function ConversationListButton({
  conversation,
  selected,
  onSelect,
}: {
  conversation: ConversationSummary;
  selected: ConversationSummary | undefined;
  onSelect: (conversation: ConversationSummary) => void;
}) {
  const selectedClass = isSelected(conversation, selected)
    ? "conversation-list-item__button--selected"
    : "";
  return (
    <button
      type="button"
      className={`conversation-list-item__button ${selectedClass}`}
      onClick={() => onSelect(conversation)}
    >
      <strong>{conversation.agent_name}</strong>
      <span>{conversation.message_count} 条消息</span>
      <time>{formatDateTime(conversation.latest_message_at)}</time>
      {conversation.active_run_count ? <Tag color="processing">进行中</Tag> : null}
    </button>
  );
}

function ConversationMessages({
  messages,
  error,
  loading,
  selected,
  onViewRun,
}: {
  messages: ConversationMessage[];
  error: unknown;
  loading: boolean;
  selected: ConversationSummary | undefined;
  onViewRun: (interactionId: string) => void;
}) {
  const visibleMessages = messages.filter(hasMessageContent);

  return (
    <section className="conversation-workspace__messages" aria-label="对话内容">
      {!selected ? <Empty description="选择一段对话以查看消息" /> : null}
      {loading ? <Spin /> : null}
      {error ? <Empty description="对话消息暂不可用" /> : null}
      {selected && !loading && !error && !visibleMessages.length ? (
        <Empty description="该会话暂无有效消息" />
      ) : null}
      <div className="conversation-message-list">
        {visibleMessages.map((message) => (
          <ConversationMessageBubble key={message.id} message={message} onViewRun={onViewRun} />
        ))}
      </div>
    </section>
  );
}

function ConversationMessageBubble({
  message,
  onViewRun,
}: {
  message: ConversationMessage;
  onViewRun: (interactionId: string) => void;
}) {
  const isUser = message.role === "user";
  const className = isUser
    ? "conversation-message conversation-message--user"
    : "conversation-message conversation-message--assistant";
  const body = isUser ? message.content : <MarkdownPreview value={message.content} />;
  return (
    <article className={className}>
      {isUser ? (
        <button
          type="button"
          className="conversation-message__bubble conversation-message__bubble--interactive"
          onClick={() => onViewRun(message.interaction_id)}
          aria-label="查看此用户输入产生的任务"
        >
          {body}
        </button>
      ) : (
        <div className="conversation-message__bubble">{body}</div>
      )}
      <footer>
        <time>{formatDateTime(message.created_at)}</time>
        {isUser ? <span>查看本轮任务</span> : null}
        {shouldShowRunStatus(message) ? (
          <Tag color={runStatusColor(message.run_status)}>{message.run_status}</Tag>
        ) : null}
      </footer>
    </article>
  );
}

function hasMessageContent(message: ConversationMessage) {
  return message.content.trim().length > 0;
}

function shouldShowRunStatus(message: ConversationMessage) {
  return message.role === "user" && message.run_status !== "completed";
}

function runStatusColor(status: string) {
  if (status === "completed") return "success";
  if (status === "failed" || status === "cancelled") return "error";
  if (status === "partial") return "warning";
  return "processing";
}

function isSelected(conversation: ConversationSummary, selected: ConversationSummary | undefined) {
  return conversation.conversation_id === selected?.conversation_id;
}
