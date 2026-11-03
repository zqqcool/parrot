import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert } from "antd";
import { Link, useParams } from "react-router-dom";

import { KnowledgeRetrievalWorkspace } from "@/features/admin/KnowledgeRetrievalWorkspace";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import type { KnowledgeSpace } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { AdminPageHeader, RequestErrorAlert } from "@/shared/ui";

import "./knowledge-retrieval-page.css";

export function KnowledgeRetrievalPage() {
  const tenantId = useTenantId();
  const { spaceId } = useParams();
  const auth = useAuth();
  const client = useQueryClient();
  const spaces = useQuery({
    queryKey: ["admin", tenantId, "knowledge-spaces"],
    queryFn: () => adminApi.listKnowledgeSpaces(tenantId ?? ""),
    enabled: Boolean(tenantId),
  });
  const space = (spaces.data ?? []).find((item) => item.id === spaceId);

  if (!tenantId) return <TenantRequiredState />;

  const header = (
    <AdminPageHeader
      title={space ? `${space.name} · 召回测试` : "召回测试"}
      description="输入真实用户问题，检查当前知识库已发布片段的召回顺序与内容。"
      breadcrumbs={[
        { title: <Link to="/admin">工作台</Link> },
        { title: <Link to="/admin/knowledge">知识库</Link> },
        {
          title: (
            <Link to={`/admin/knowledge/${spaceId ?? ""}/documents`}>{space?.name ?? "文档"}</Link>
          ),
        },
        { title: "召回测试" },
      ]}
    />
  );

  if (spaces.isPending) {
    return (
      <section className="knowledge-retrieval-page">
        {header}
        <p role="status">正在加载知识库…</p>
      </section>
    );
  }
  if (spaces.isError) {
    return (
      <section className="knowledge-retrieval-page">
        {header}
        <RequestErrorAlert error={spaces.error} fallback="加载知识库失败" />
      </section>
    );
  }
  if (!space) {
    return (
      <section className="knowledge-retrieval-page">
        {header}
        <Alert showIcon type="info" message="知识库不存在，或当前账号没有查询权限。" />
      </section>
    );
  }

  return (
    <section className="knowledge-retrieval-page">
      {header}
      <KnowledgeRetrievalWorkspace
        canManage={auth.hasPermission("knowledge.spaces.manage")}
        space={space}
        tenantId={tenantId}
        onSettingsUpdated={(updated) => {
          client.setQueryData<KnowledgeSpace[]>(
            ["admin", tenantId, "knowledge-spaces"],
            (current) => current?.map((item) => (item.id === updated.id ? updated : item)),
          );
        }}
      />
    </section>
  );
}
