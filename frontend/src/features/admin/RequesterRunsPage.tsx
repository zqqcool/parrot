import { useState } from "react";
import { Result } from "antd";
import { Link, useParams } from "react-router-dom";

import { RunDetailDrawer } from "@/features/admin/RunDetailDrawer";
import { ConversationWorkspace } from "@/features/admin/requester-conversations/ConversationWorkspace";
import { useRequesterConversationWorkspace } from "@/features/admin/requester-conversations/useRequesterConversationWorkspace";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { useTenantId } from "@/features/admin/useTenant";
import { AdminPageHeader, RequestErrorAlert } from "@/shared/ui";

type RequesterRoute = {
  actorId: string;
  actorType: string;
};

function parseRequesterRoute(params: Record<string, string | undefined>): RequesterRoute | null {
  const { actorId, actorType } = params;
  if (!actorId || !actorType) return null;

  return { actorId, actorType };
}

export function RequesterRunsPage() {
  const requester = parseRequesterRoute(useParams());
  const tenantId = useTenantId();
  const [selectedRunId, setSelectedRunId] = useState<string>();
  const workspace = useRequesterConversationWorkspace(tenantId, requester);

  if (!tenantId) return <TenantRequiredState />;
  if (!requester) return <Result status="404" title="提问用户不存在" />;

  return (
    <section>
      <AdminPageHeader
        title="用户对话"
        description="按运行时会话展示持久化的用户与智能体消息；点击用户输入可查看该轮任务。"
        breadcrumbs={[
          { title: <Link to="/admin">工作台</Link> },
          { title: <Link to="/admin/runs">运行进度</Link> },
          { title: "用户对话" },
        ]}
      />
      <RequestErrorAlert error={workspace.conversations.error} fallback="加载用户对话失败" />
      <ConversationWorkspace
        conversations={workspace.conversations.data ?? []}
        conversationsLoading={workspace.conversations.isPending}
        messages={workspace.messages.data ?? []}
        messagesError={workspace.messages.error}
        messagesLoading={Boolean(workspace.selected) && workspace.messages.isPending}
        selectedConversation={workspace.selected}
        onSelectConversation={workspace.select}
        onViewRun={setSelectedRunId}
      />
      {selectedRunId ? (
        <RunDetailDrawer runId={selectedRunId} onClose={() => setSelectedRunId(undefined)} />
      ) : null}
    </section>
  );
}
