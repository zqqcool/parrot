import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Descriptions, Popconfirm, Result, Switch, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import type { Skill, SkillVersion } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { formatDateTime } from "@/shared/time";
import { AdminPageHeader, DataTable, RequestErrorAlert, UserIdentity } from "@/shared/ui";

// This component coordinates independent query and mutation states for one page.
// eslint-disable-next-line complexity
export function SkillDetailPage() {
  const { skillId = "" } = useParams();
  const tenantId = useTenantId();
  const navigate = useNavigate();
  const auth = useAuth();
  const client = useQueryClient();
  const skillsQuery = useQuery({
    queryKey: ["admin", tenantId, "skills"],
    queryFn: () => adminApi.listSkills(tenantId ?? ""),
    enabled: Boolean(tenantId),
  });
  const skill = skillsQuery.data?.find((item) => item.id === skillId);
  const versionsQuery = useQuery({
    queryKey: ["admin", tenantId, "skills", skillId, "versions"],
    queryFn: () => adminApi.listSkillVersions(tenantId ?? "", skillId),
    enabled: Boolean(tenantId && skill),
  });
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["admin", tenantId, "skills"] });
    await client.invalidateQueries({
      queryKey: ["admin", tenantId, "skills", skillId, "versions"],
    });
  };
  const fork = useMutation({
    mutationFn: (versionId: string) => adminApi.forkSkillDraft(tenantId ?? "", skillId, versionId),
    onSuccess: async () => {
      await refresh();
      void navigate(`/admin/skills/${skillId}/edit`);
    },
  });
  const rollback = useMutation({
    mutationFn: (versionId: string) => adminApi.rollbackSkill(tenantId ?? "", skillId, versionId),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => adminApi.deleteSkill(tenantId ?? "", skillId),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "skills"] });
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "dashboard"] });
      void navigate("/admin/skills");
    },
  });

  if (!tenantId) return <Result status="404" title="请先选择租户" />;
  if (skillsQuery.isPending) return <Result status="info" title="正在加载 Skill" />;
  if (!skill) return <Result status="404" title="Skill 不存在或无权查看" />;

  const canManage = auth.hasPermission("skills.manage");
  return (
    <section className="skill-detail-page">
      <AdminPageHeader
        action={
          canManage ? (
            <Popconfirm
              cancelText="取消"
              description="仅未绑定到任何 Agent 的 Skill 可删除；版本历史一并删除且无法恢复。"
              okButtonProps={{ danger: true, loading: remove.isPending }}
              okText="确认删除"
              title={`删除 Skill “${skill.name}”？`}
              onConfirm={() => remove.mutate()}
            >
              <Button danger loading={remove.isPending}>
                删除 Skill
              </Button>
            </Popconfirm>
          ) : null
        }
        breadcrumbs={[
          { title: <Link to="/admin">工作台</Link> },
          { title: <Link to="/admin/skills">Skill 管理</Link> },
          { title: skill.name },
        ]}
        description={skill.description || "暂无说明"}
        title={skill.name}
      />
      <Descriptions
        colon={false}
        className="skill-detail-summary"
        column={{ xl: 4, lg: 3, md: 2, sm: 1, xs: 1 }}
        items={summaryItems(skill)}
        size="small"
      />
      {fork.error || rollback.error || remove.error ? (
        <RequestErrorAlert
          error={fork.error ?? rollback.error ?? remove.error}
          fallback="Skill 操作失败，请稍后重试。"
        />
      ) : null}
      <section className="skill-version-history">
        <h2>版本历史</h2>
        <p>已发布版本不可修改。回滚只切换当前运行版本；基于历史版本编辑会创建一个独立草稿。</p>
        <DataTable
          columns={columns(skill, canManage, navigate, fork, rollback)}
          dataSource={versionsQuery.data ?? []}
          loading={versionsQuery.isPending}
          rowKey="id"
          scroll={{ x: 920 }}
        />
      </section>
    </section>
  );
}

function summaryItems(skill: Skill) {
  return [
    { key: "current", label: "当前版本", children: `v${skill.version}` },
    { key: "status", label: "状态", children: <SkillStatus status={skill.status} /> },
    {
      key: "availability",
      label: "启用",
      children: <SkillAvailability status={skill.status} />,
    },
    { key: "draft", label: "草稿", children: skill.has_draft ? "有待发布草稿" : "无" },
    { key: "id", label: "Skill ID", children: skill.id },
    { key: "package", label: "当前文件包", children: skill.package_filename ?? "旧版文本 Skill" },
  ];
}

function columns(
  skill: Skill,
  canManage: boolean,
  navigate: ReturnType<typeof useNavigate>,
  fork: VersionMutation,
  rollback: VersionMutation,
): ColumnsType<SkillVersion> {
  return [
    { title: "版本", dataIndex: "version", width: 90, render: (value) => `v${value}` },
    {
      title: "状态",
      dataIndex: "status",
      width: 110,
      render: (_value, version) => <SkillStatus status={version.status} />,
    },
    { title: "校验和", dataIndex: "package_sha256", ellipsis: true, width: 220 },
    {
      title: "发布人",
      dataIndex: "published_by_user",
      width: 140,
      render: (_value, version) => (
        <UserIdentity tenantId={skill.tenant_id} user={version.published_by_user} />
      ),
    },
    {
      title: "发布时间",
      dataIndex: "published_at",
      width: 180,
      render: (_value, version) => formatDateTime(version.published_at),
    },
    {
      title: "操作",
      key: "actions",
      fixed: "right",
      width: 250,
      render: (_, version) => {
        if (!canManage) return null;
        if (version.status === "draft") {
          return (
            <Button
              size="small"
              type="link"
              onClick={() => void navigate(`/admin/skills/${skill.id}/edit`)}
            >
              编辑草稿
            </Button>
          );
        }
        if (version.status !== "published") return null;
        return (
          <div className="skill-version-actions">
            <Button
              loading={fork.isPending && fork.variables === version.id}
              size="small"
              onClick={() => fork.mutate(version.id)}
            >
              基于此版本编辑
            </Button>
            {skill.current_version_id !== version.id ? (
              <Button
                danger
                loading={rollback.isPending && rollback.variables === version.id}
                size="small"
                onClick={() => rollback.mutate(version.id)}
              >
                回滚
              </Button>
            ) : (
              <Tag color="green">当前</Tag>
            )}
          </div>
        );
      },
    },
  ];
}

type VersionMutation = {
  isPending: boolean;
  mutate: (versionId: string) => void;
  variables?: string;
};

function SkillStatus({ status }: { status: string }) {
  if (status === "published") return <Tag color="green">已发布</Tag>;
  if (status === "disabled") return <Tag color="red">已停用</Tag>;
  return <Tag color="gold">草稿</Tag>;
}

function SkillAvailability({ status }: { status: string }) {
  const enabled = status === "published";
  const label = enabled ? "已开启" : status === "disabled" ? "已停用" : "未发布";
  return (
    <span className="skill-availability">
      <Switch
        aria-label="Skill 启用状态"
        checked={enabled}
        checkedChildren="开"
        disabled
        size="small"
        unCheckedChildren="关"
      />
      <span>{label}</span>
    </span>
  );
}
