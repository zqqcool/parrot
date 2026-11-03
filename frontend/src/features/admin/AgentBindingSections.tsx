import type { ReactNode } from "react";
import { Button, Popconfirm, Result, Space, Spin } from "antd";
import { useNavigate } from "react-router-dom";

import type { AdminAgent as Agent } from "@/shared/api/types";
import { AppIcon } from "@/shared/icons";
import { BinaryStatusTag } from "@/shared/ui";

export function LoadState({
  error,
  pending,
  children,
}: {
  error: unknown;
  pending: boolean;
  children: ReactNode;
}) {
  if (error) {
    return <Result status="error" title="运行配置暂不可用" />;
  }
  if (pending) return <Spin />;
  return children;
}

export function BasicSection({
  agent,
  canManage,
  onEditBasic,
  onEditSystemPrompt,
  children,
}: {
  agent: Agent;
  canManage: boolean;
  onEditBasic: () => void;
  onEditSystemPrompt: () => void;
  children?: ReactNode;
}) {
  const navigate = useNavigate();

  return (
    <section className="agent-tab-panel">
      <div className="agent-tab-heading">
        <div>
          <h2>基本资料</h2>
          <p>管理智能体的身份信息与运行指令；访问范围和发布状态在下方单独控制。</p>
        </div>
        <Space size={8} wrap>
          {canManage ? (
            <Button
              icon={<AppIcon name="EditTwo" size="sm" />}
              type="primary"
              onClick={onEditBasic}
            >
              编辑基本资料
            </Button>
          ) : null}
          {agent.published ? (
            <Button
              icon={<AppIcon name="ArrowRight" size="sm" />}
              iconPosition="end"
              onClick={() => void navigate(`/agents/${agent.slug}`)}
            >
              体验智能体
            </Button>
          ) : null}
        </Space>
      </div>
      <dl className="agent-basic-details" aria-label="智能体基本资料">
        <BasicDetail label="名称" value={agent.name} />
        <BasicDetail label="公开标识" value={agent.slug} />
        <BasicDetail label="智能体类型" value={agent.agent_type_key} />
        <BasicDetail label="运行时 ID" value={agent.runtime_agent_id} />
        <BasicDetail
          className="agent-basic-details-description"
          label="说明"
          value={agent.description || "暂无说明"}
        />
      </dl>
      <section className="agent-prompt-section" aria-labelledby="agent-system-prompt-heading">
        <div className="agent-prompt-section-heading">
          <div>
            <h3 id="agent-system-prompt-heading">系统提示词</h3>
            <p>定义角色、行为边界和输出规则；运行时会将其作为专属指令传入模型。</p>
          </div>
          {canManage ? (
            <Button icon={<AppIcon name="EditTwo" size="sm" />} onClick={onEditSystemPrompt}>
              编辑提示词
            </Button>
          ) : null}
        </div>
        <div className="agent-system-prompt" aria-label="Agent 系统提示词">
          {agent.system_prompt ? (
            <pre>{agent.system_prompt}</pre>
          ) : (
            <p>尚未配置系统提示词。编辑后将应用到后续运行。</p>
          )}
        </div>
      </section>
      {children}
    </section>
  );
}

function BasicDetail({
  className,
  label,
  value,
}: {
  className?: string;
  label: string;
  value: string;
}) {
  return (
    <div className={className}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

type AccessSectionProps = {
  agent: Agent;
  canManage: boolean;
  canPublish: boolean;
  publishPending: boolean;
  statusPending: boolean;
  onPublish: () => void;
  onStatusChange: () => void;
  onEditAnonymousAccess: () => void;
};

export function AccessSection({
  agent,
  canManage,
  canPublish,
  publishPending,
  statusPending,
  onPublish,
  onStatusChange,
  onEditAnonymousAccess,
}: AccessSectionProps) {
  const isActive = agent.status === "active";
  const canChangePublication = canManage && canPublish;

  return (
    <section className="agent-access-section" aria-labelledby="agent-access-heading">
      <div>
        <h2 id="agent-access-heading">访问与发布</h2>
        <p>高影响状态需要单独确认；匿名访问范围可在对应卡片内单独调整。</p>
      </div>
      <div className="agent-access-grid">
        <AccessSetting
          action={
            <RuntimeStatusAction
              canManage={canManage}
              isActive={isActive}
              loading={statusPending}
              onConfirm={onStatusChange}
            />
          }
          description={runtimeStatusDescription(isActive)}
          label="运行状态"
          status={<BinaryStatusTag active={isActive} activeLabel="已启用" inactiveLabel="已停用" />}
        />
        <AccessSetting
          action={
            <PublicationAction
              canChange={canChangePublication}
              loading={publishPending}
              onConfirm={onPublish}
              published={agent.published}
            />
          }
          description={publicationDescription(canManage, canPublish)}
          label="公开发布"
          status={
            <BinaryStatusTag active={agent.published} activeLabel="已发布" inactiveLabel="草稿" />
          }
        />
        <AccessSetting
          action={canManage ? <Button onClick={onEditAnonymousAccess}>调整访问范围</Button> : null}
          description={
            agent.allow_anonymous
              ? "未登录访客可访问已发布且已启用的智能体。"
              : "仅已登录且获授权的用户可访问。"
          }
          label="匿名访问"
          status={
            <BinaryStatusTag
              active={agent.allow_anonymous}
              activeLabel="允许"
              inactiveLabel="禁止"
            />
          }
        />
      </div>
    </section>
  );
}

function RuntimeStatusAction({
  canManage,
  isActive,
  loading,
  onConfirm,
}: {
  canManage: boolean;
  isActive: boolean;
  loading: boolean;
  onConfirm: () => void;
}) {
  if (!canManage) return null;
  const action = runtimeStatusAction(isActive);
  return (
    <Popconfirm
      cancelText="取消"
      okText={`确认${action}`}
      onConfirm={onConfirm}
      title={`确认${action}该智能体？`}
    >
      <Button danger={isActive} loading={loading}>
        {action}运行
      </Button>
    </Popconfirm>
  );
}

function PublicationAction({
  canChange,
  loading,
  onConfirm,
  published,
}: {
  canChange: boolean;
  loading: boolean;
  onConfirm: () => void;
  published: boolean;
}) {
  if (!canChange) return null;
  const action = published ? "下线" : "发布";
  return (
    <Popconfirm
      cancelText="取消"
      okText={`确认${action}`}
      onConfirm={onConfirm}
      title={`确认${action}该智能体？`}
    >
      <Button danger={published} loading={loading} type={published ? "default" : "primary"}>
        {action}
      </Button>
    </Popconfirm>
  );
}

function runtimeStatusAction(isActive: boolean) {
  return isActive ? "停用" : "启用";
}

function runtimeStatusDescription(isActive: boolean) {
  return isActive ? "停用后将拒绝新的交互请求。" : "启用后可继续处理已发布的访问请求。";
}

function publicationDescription(canManage: boolean, canPublish: boolean) {
  if (canPublish && !canManage) return "发布操作还需要智能体配置权限。";
  return "发布前需配置默认 LLM；下线不会删除配置。";
}

function AccessSetting({
  action,
  description,
  label,
  status,
}: {
  action: ReactNode;
  description: string;
  label: string;
  status: ReactNode;
}) {
  return (
    <section className="agent-access-setting">
      <div className="agent-access-setting-heading">
        <h3>{label}</h3>
        {status}
      </div>
      <p>{description}</p>
      {action}
    </section>
  );
}
