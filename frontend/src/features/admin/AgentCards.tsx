import { Avatar, Button, Card, Empty, Skeleton, Tag } from "antd";
import { Link } from "react-router-dom";

import type { AdminAgent as Agent } from "@/shared/api/types";
import { endpoints } from "@/shared/api/endpoints";
import { AppIcon } from "@/shared/icons";
import { BinaryStatusTag } from "@/shared/ui";

import "./agent-cards.css";

type Props = {
  agents: Agent[] | undefined;
  agentTypeNames: ReadonlyMap<string, string>;
  tenantId: string;
  loading: boolean;
  onView: (agent: Agent) => void;
};

export function AgentCards({ agents, agentTypeNames, loading, onView, tenantId }: Props) {
  if (loading) return <AgentCardSkeletons />;
  if (!agents?.length) return <Empty className="agent-management-empty" description="暂无智能体" />;

  return (
    <div className="agent-management-grid">
      {agents.map((agent) => (
        <AgentCard
          agent={agent}
          agentTypeName={agentTypeNames.get(agent.agent_type_key) ?? agent.agent_type_key}
          key={agent.id}
          tenantId={tenantId}
          onView={onView}
        />
      ))}
    </div>
  );
}

function AgentCard({
  agent,
  agentTypeName,
  tenantId,
  onView,
}: Omit<Props, "agents" | "agentTypeNames" | "loading"> & {
  agent: Agent;
  agentTypeName: string;
}) {
  const runtimeStatus = agent.status === "active" ? "运行中" : "已停用";

  return (
    <article
      aria-label={`智能体 ${agent.name}`}
      className={`agent-management-card ${agent.published ? "is-published" : "is-draft"}`}
    >
      <Card hoverable>
        <div className="agent-card-heading">
          <Avatar
            alt={`${agent.name} 头像`}
            className="agent-card-avatar"
            icon={!agent.avatar_present ? <AppIcon name="RobotOne" size="xl" /> : undefined}
            shape="circle"
            size={48}
            src={agent.avatar_present ? endpoints.admin.agentAvatar(tenantId, agent.id) : undefined}
          />
          <div className="agent-card-title">
            <h2>{agent.name}</h2>
            <span className="agent-card-slug">/{agent.slug}</span>
          </div>
          <BinaryStatusTag active={agent.published} activeLabel="已发布" inactiveLabel="草稿" />
        </div>
        <p className="agent-card-description">{agent.description || "暂无说明"}</p>
        <div className="agent-card-tags" aria-label="智能体属性">
          <Tag color="blue" icon={<AppIcon name="ApplicationOne" size="xs" />}>
            {agentTypeName}
          </Tag>
          <Tag icon={<AppIcon name={agent.allow_anonymous ? "User" : "Lock"} size="xs" />}>
            {agent.allow_anonymous ? "支持匿名访问" : "需登录访问"}
          </Tag>
        </div>
        <dl className="agent-card-details">
          <div>
            <dt>运行状态</dt>
            <dd className={agent.status === "active" ? "is-active" : "is-disabled"}>
              <span aria-hidden="true" className="agent-card-status-dot" />
              {runtimeStatus}
            </dd>
          </div>
          <div>
            <dt>运行时 ID</dt>
            <dd title={agent.runtime_agent_id}>{agent.runtime_agent_id}</dd>
          </div>
        </dl>
        <div className="agent-card-actions">
          <Button
            icon={<AppIcon name="SettingTwo" size="sm" />}
            size="small"
            type="primary"
            onClick={() => onView(agent)}
          >
            管理配置
          </Button>
          {agent.published ? (
            <Link className="agent-card-link" to={`/agents/${agent.slug}`}>
              在线体验
              <AppIcon name="ArrowRight" size="sm" />
            </Link>
          ) : null}
        </div>
      </Card>
    </article>
  );
}

function AgentCardSkeletons() {
  return (
    <div aria-label="正在加载智能体" className="agent-management-grid" role="status">
      {Array.from({ length: 3 }, (_, index) => (
        <Card className="agent-management-card" key={index}>
          <Skeleton active paragraph={{ rows: 3 }} title />
        </Card>
      ))}
    </div>
  );
}
