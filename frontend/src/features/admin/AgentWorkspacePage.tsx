import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Breadcrumb, Card, Result, Skeleton, Space, message } from "antd";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { AgentAnonymousAccessEditor } from "@/features/admin/AgentAnonymousAccessEditor";
import { AgentBasicEditor } from "@/features/admin/AgentBasicEditor";
import { AgentBindingsEditor } from "@/features/admin/AgentBindingsEditor";
import { AgentSystemPromptEditor } from "@/features/admin/AgentSystemPromptEditor";
import { useTenantId } from "@/features/admin/useTenant";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { adminApi } from "@/shared/api/client";
import { endpoints } from "@/shared/api/endpoints";
import type { AdminAgent as Agent, AgentType } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { AppIcon } from "@/shared/icons";
import { BinaryStatusTag } from "@/shared/ui";

import "./agent-workspace.css";

const configurationTabs = new Set([
  "basic",
  "llm",
  "skills",
  "schedules",
  "mcp",
  "knowledge",
  "integrations",
]);

type ActiveEditor = "anonymousAccess" | "basic" | "systemPrompt" | null;

function AgentSummary({ agent, tenantId }: { agent: Agent; tenantId: string }) {
  return (
    <Card className="agent-workspace-summary">
      <div className="agent-workspace-summary-header">
        <div className="agent-workspace-summary-main">
          <span className="agent-workspace-avatar">
            {agent.avatar_present ? (
              <img alt="" src={endpoints.admin.agentAvatar(tenantId, agent.id)} />
            ) : (
              <AppIcon name="RobotOne" size="2xl" />
            )}
          </span>
          <div>
            <Space size={8} wrap>
              <h2>{agent.name}</h2>
              <BinaryStatusTag active={agent.published} activeLabel="已发布" inactiveLabel="草稿" />
            </Space>
            <p>{agent.description || "暂无说明"}</p>
          </div>
        </div>
        <div className="agent-workspace-summary-status" aria-label="智能体状态">
          <SummaryStatus label="发布状态" value={agent.published ? "已发布" : "草稿"} />
          <SummaryStatus label="匿名访问" value={agent.allow_anonymous ? "允许" : "禁止"} />
          <SummaryStatus label="运行状态" value={agent.status === "active" ? "启用" : "停用"} />
        </div>
      </div>
      <dl className="agent-workspace-summary-details" aria-label="智能体运行信息">
        <SummaryDetail label="公开标识" value={agent.slug} />
        <SummaryDetail label="运行时 ID" value={agent.runtime_agent_id} />
        <SummaryDetail label="智能体类型" value={agent.agent_type_key} />
      </dl>
    </Card>
  );
}

function SummaryStatus({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SummaryDetail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

type AgentWorkspaceContentProps = {
  agent: Agent;
  agentType: AgentType;
  canManage: boolean;
  canManageSchedules: boolean;
  canQuery: boolean;
  canPublish: boolean;
  canReadKnowledge: boolean;
  canReadMcp: boolean;
  tenantId: string;
  activeTab: string;
  onTabChange: (tab: string) => void;
};

function AgentWorkspaceContent({
  agent,
  agentType,
  canManage,
  canManageSchedules,
  canQuery,
  canPublish,
  canReadKnowledge,
  canReadMcp,
  tenantId,
  activeTab,
  onTabChange,
}: AgentWorkspaceContentProps) {
  const [activeEditor, setActiveEditor] = useState<ActiveEditor>(null);
  const [messageApi, messageContext] = message.useMessage();
  const onSuccessMessage = (content: string) => void messageApi.success(content);

  return (
    <section className="agent-workspace-page">
      {messageContext}
      <header className="agent-workspace-header">
        <h1 className="agent-workspace-title">智能体详情</h1>
        <Breadcrumb
          items={[
            { title: <Link to="/admin">工作台</Link> },
            { title: <Link to="/admin/agents">智能体管理</Link> },
            { title: agent.name },
          ]}
        />
      </header>
      {activeEditor === "basic" ? (
        <AgentBasicEditor
          agent={agent}
          tenantId={tenantId}
          open
          onClose={() => setActiveEditor(null)}
          onSuccessMessage={onSuccessMessage}
        />
      ) : null}
      {activeEditor === "systemPrompt" ? (
        <AgentSystemPromptEditor
          agent={agent}
          tenantId={tenantId}
          open
          onClose={() => setActiveEditor(null)}
          onSuccessMessage={onSuccessMessage}
        />
      ) : null}
      {activeEditor === "anonymousAccess" ? (
        <AgentAnonymousAccessEditor
          agent={agent}
          tenantId={tenantId}
          open
          onClose={() => setActiveEditor(null)}
          onSuccessMessage={onSuccessMessage}
        />
      ) : null}
      <AgentSummary agent={agent} tenantId={tenantId} />
      <AgentBindingsEditor
        tenantId={tenantId}
        agent={agent}
        agentType={agentType}
        canManage={canManage}
        canManageSchedules={canManageSchedules}
        canQuery={canQuery}
        canPublish={canPublish}
        canReadKnowledge={canReadKnowledge}
        canReadMcp={canReadMcp}
        activeTab={activeTab}
        onTabChange={onTabChange}
        onSuccessMessage={onSuccessMessage}
        onEditAnonymousAccess={() => setActiveEditor("anonymousAccess")}
        onEditBasic={() => setActiveEditor("basic")}
        onEditSystemPrompt={() => setActiveEditor("systemPrompt")}
      />
    </section>
  );
}

function AgentWorkspaceLoader({
  activeTab,
  agentId,
  onTabChange,
  tenantId,
}: {
  activeTab: string;
  agentId: string | undefined;
  onTabChange: (tab: string) => void;
  tenantId: string;
}) {
  const auth = useAuth();
  const query = useQuery({
    queryKey: ["admin", tenantId, "agents"],
    queryFn: () => adminApi.listAgents(tenantId),
  });
  const agentTypes = useQuery({
    queryKey: ["admin", "agent-types"],
    queryFn: () => adminApi.listAgentTypes(),
  });
  const agent = query.data?.find((item) => item.id === agentId);
  const agentType = agentTypes.data?.find((item) => item.key === agent?.agent_type_key);

  if (query.isPending || agentTypes.isPending) return <Skeleton active paragraph={{ rows: 8 }} />;
  if (query.error || agentTypes.error) return <Result status="error" title="智能体暂不可用" />;
  if (!agent) return <Result status="404" title="智能体不存在或已不可见" />;
  if (!agentType) return <Result status="error" title="智能体类型配置不可用" />;

  return (
    <AgentWorkspaceContent
      agent={agent}
      agentType={agentType}
      canManage={auth.hasPermission("agents.manage")}
      canManageSchedules={auth.hasPermission("schedules.manage")}
      canQuery={auth.hasPermission("knowledge.query")}
      canPublish={auth.hasPermission("agents.publish")}
      canReadKnowledge={auth.hasPermission("knowledge.spaces.read")}
      canReadMcp={auth.hasPermission("mcp_servers.read")}
      tenantId={tenantId}
      activeTab={activeTab}
      onTabChange={onTabChange}
    />
  );
}

export function AgentWorkspacePage() {
  const { agentId } = useParams();
  const tenantId = useTenantId();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab") ?? "";
  const activeTab = configurationTabs.has(requestedTab) ? requestedTab : "basic";

  if (!tenantId) return <TenantRequiredState />;

  return (
    <AgentWorkspaceLoader
      activeTab={activeTab}
      agentId={agentId}
      onTabChange={(tab) => setSearchParams({ tab })}
      tenantId={tenantId}
    />
  );
}
