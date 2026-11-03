import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { adminApi } from "@/shared/api/client";
import type { ConversationSummary } from "@/shared/api/types";

type RequesterRoute = { actorId: string; actorType: string };

export function useRequesterConversationWorkspace(
  tenantId: string | null,
  requester: RequesterRoute | null,
) {
  const [searchParams, setSearchParams] = useSearchParams();
  const conversations = useQuery({
    queryKey: ["admin", tenantId, "runs", "conversations", requester],
    queryFn: () => loadConversations(tenantId, requester),
    enabled: Boolean(tenantId && requester),
    refetchInterval: (query) => (hasActiveConversation(query.state.data) ? 5_000 : false),
  });
  const selected = selectedConversation(conversations.data, searchParams);
  const messages = useQuery({
    queryKey: ["admin", tenantId, "runs", "conversation-messages", requester, selected],
    queryFn: () => loadMessages(tenantId, requester, selected),
    enabled: Boolean(tenantId && requester && selected),
    refetchInterval: selected?.active_run_count ? 5_000 : false,
  });

  useEffect(() => {
    if (!conversations.data?.length || selected) return;
    setConversationSearch(conversations.data[0], setSearchParams);
  }, [conversations.data, selected, setSearchParams]);

  return {
    conversations,
    messages,
    selected,
    select: (conversation: ConversationSummary) =>
      setConversationSearch(conversation, setSearchParams),
  };
}

function loadConversations(tenantId: string | null, requester: RequesterRoute | null) {
  return adminApi.listRunConversations(tenantId ?? "", {
    actorId: requester?.actorId ?? "",
    actorType: requester?.actorType ?? "",
  });
}

function loadMessages(
  tenantId: string | null,
  requester: RequesterRoute | null,
  conversation: ConversationSummary | undefined,
) {
  return adminApi.listRunConversationMessages(tenantId ?? "", {
    actorId: requester?.actorId ?? "",
    actorType: requester?.actorType ?? "",
    conversationId: conversation?.conversation_id ?? "",
  });
}

function hasActiveConversation(conversations: ConversationSummary[] | undefined) {
  return conversations?.some((conversation) => conversation.active_run_count > 0) ?? false;
}

function selectedConversation(
  conversations: ConversationSummary[] | undefined,
  search: URLSearchParams,
) {
  const conversationId = search.get("conversation");
  return conversations?.find((conversation) => conversation.conversation_id === conversationId);
}

function setConversationSearch(
  conversation: ConversationSummary,
  setSearchParams: ReturnType<typeof useSearchParams>[1],
) {
  setSearchParams(conversationSearchParams(conversation), { replace: true });
}

function conversationSearchParams(conversation: ConversationSummary) {
  return new URLSearchParams({ conversation: conversation.conversation_id });
}
