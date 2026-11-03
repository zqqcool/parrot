import { Button, Empty, Space } from "antd";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { LlmConfig, Skill } from "@/shared/api/types";
import { BinaryStatusTag, DataTable, RequestErrorAlert } from "@/shared/ui";

type LlmSectionProps = {
  canManage: boolean;
  error: unknown;
  items: LlmConfig[];
  onSelect: (id: string) => void;
  selectedId?: string;
  selectingId?: string;
};

export function LlmSection({
  canManage,
  error,
  items,
  onSelect,
  selectedId,
  selectingId,
}: LlmSectionProps) {
  const availableItems = items.filter((item) => item.status === "active");
  return (
    <section className="agent-tab-panel">
      <TabHeading
        title="可用模型配置"
        action={
          <Space>
            <Link className="ant-btn" to="/admin/llm-configs">
              管理模型配置
            </Link>
          </Space>
        }
      />
      {availableItems.length ? (
        <DataTable<LlmConfig>
          rowKey="id"
          className="agent-tab-table"
          dataSource={availableItems}
          scroll={{ x: 1040 }}
          columns={[
            {
              title: "当前 Agent",
              key: "binding",
              width: 128,
              render: (_, item) =>
                selectedId === item.id ? (
                  <BinaryStatusTag
                    active
                    activeLabel="当前模型"
                    inactiveLabel=""
                    activeColor="green"
                  />
                ) : (
                  "-"
                ),
            },
            { title: "名称", dataIndex: "name", width: 170, ellipsis: true },
            { title: "模型", dataIndex: "model", width: 200, ellipsis: true },
            { title: "供应商", dataIndex: "provider", width: 170, ellipsis: true },
            { title: "Base URL", dataIndex: "base_url", ellipsis: true },
            {
              title: "状态",
              dataIndex: "status",
              width: 100,
              render: (status: string) => (
                <BinaryStatusTag
                  active={status === "active"}
                  activeLabel="启用"
                  inactiveLabel="停用"
                />
              ),
            },
            {
              title: "操作",
              key: "action",
              width: 120,
              render: (_, item) => {
                if (selectedId === item.id) {
                  return (
                    <Button disabled size="small" type="link">
                      当前模型
                    </Button>
                  );
                }
                return (
                  <Button
                    disabled={!canManage || Boolean(selectingId)}
                    loading={selectingId === item.id}
                    size="small"
                    type="primary"
                    onClick={() => onSelect(item.id)}
                  >
                    使用此模型
                  </Button>
                );
              },
            },
          ]}
        />
      ) : (
        <Empty description="当前租户没有可绑定的启用模型" />
      )}
      <RequestErrorAlert error={error} fallback="切换模型配置失败" />
    </section>
  );
}

type SkillSectionProps = {
  restrictsExecutableSkills: boolean;
  canManage: boolean;
  error: unknown;
  ids: string[];
  items: Skill[];
  onClearIncompatible: (ids: string[]) => void;
  onToggle: (id: string) => void;
  saving: boolean;
  savingSkillId?: string;
};

export function SkillSection({
  restrictsExecutableSkills,
  canManage,
  error,
  ids,
  items,
  onClearIncompatible,
  onToggle,
  saving,
  savingSkillId,
}: SkillSectionProps) {
  const publishedItems = items.filter((item) => item.status === "published");
  const availableItems = publishedItems.filter(
    (item) => !restrictsExecutableSkills || isInstructionOnlySkill(item),
  );
  const availableSkillIds = new Set(availableItems.map((item) => item.id));
  const unavailableBoundCount = ids.filter((id) => !availableSkillIds.has(id)).length;
  const incompatibleBoundIds = restrictsExecutableSkills
    ? ids.filter((id) => {
        const item = publishedItems.find((candidate) => candidate.id === id);
        return item !== undefined && !isInstructionOnlySkill(item);
      })
    : [];
  const compatibleIds = ids.filter((id) => !incompatibleBoundIds.includes(id));

  return (
    <section className="agent-tab-panel">
      <TabHeading
        title="租户 Skill 能力授权"
        description={
          incompatibleBoundIds.length
            ? `检测到 ${incompatibleBoundIds.length} 个历史可执行 Skill 绑定；知识型智能体不会使用它们，请解除绑定或切换为功能型智能体。`
            : unavailableBoundCount
              ? `有 ${unavailableBoundCount} 个已授权 Skill 当前不可用，请到 Skill 管理中恢复或取消授权。`
              : restrictsExecutableSkills
                ? `知识型智能体仅可授权说明型 Skill；系统 Skill 自动可用。已授权 ${ids.length} 个。`
                : `系统 Skill 自动可用；此处管理租户已发布 Skill。已授权 ${ids.length} 个。`
        }
        action={
          <Space>
            {incompatibleBoundIds.length ? (
              <Button
                danger
                disabled={!canManage || saving}
                loading={saving && !savingSkillId}
                onClick={() => onClearIncompatible(compatibleIds)}
              >
                解除不兼容绑定
              </Button>
            ) : null}
            <Link className="ant-btn" to="/admin/skills">
              管理租户 Skill
            </Link>
          </Space>
        }
      />
      <DataTable<Skill>
        rowKey="id"
        className="agent-tab-table"
        dataSource={availableItems}
        locale={{ emptyText: "当前租户没有可绑定的已发布 Skill" }}
        scroll={{ x: 940 }}
        columns={[
          { title: "名称", dataIndex: "name", width: 220, ellipsis: true },
          { title: "描述", dataIndex: "description", ellipsis: true },
          {
            title: "运行方式",
            key: "runtime",
            width: 132,
            render: (_, item) => skillRuntimeMode(item),
          },
          {
            title: "状态",
            dataIndex: "status",
            width: 110,
            render: (status: string) => (
              <BinaryStatusTag
                active={status === "published"}
                activeLabel="已发布"
                inactiveLabel="未发布"
              />
            ),
          },
          {
            title: "当前版本",
            dataIndex: "version",
            width: 120,
            render: (value: number) => `v${value}`,
          },
          {
            title: "操作",
            key: "action",
            width: 128,
            render: (_, item) => {
              const authorized = ids.includes(item.id);
              return (
                <Button
                  aria-label={`${authorized ? "取消授权" : "授权"} ${item.name}`}
                  danger={authorized}
                  disabled={!canManage || saving}
                  loading={saving && savingSkillId === item.id}
                  size="small"
                  type={authorized ? "link" : "primary"}
                  onClick={() => onToggle(item.id)}
                >
                  {authorized ? "取消授权" : "授权"}
                </Button>
              );
            },
          },
        ]}
      />
      <RequestErrorAlert error={error} fallback="更新 Skill 授权失败" />
    </section>
  );
}

function TabHeading({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="agent-tab-heading">
      <div>
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

function isInstructionOnlySkill(skill: Pick<Skill, "manifest">) {
  const runtime = skill.manifest.runtime;
  return !isRecord(runtime) || typeof runtime.entrypoint !== "string";
}

function skillRuntimeMode(skill: Skill) {
  return isInstructionOnlySkill(skill) ? "加载说明" : "沙箱执行";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
