import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Breadcrumb } from "antd";
import { Link, useNavigate, useParams } from "react-router-dom";

import { KnowledgeDocumentsPanel } from "@/features/admin/KnowledgeDocumentsPanel";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import type { KnowledgeSpace } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { RequestErrorAlert } from "@/shared/ui";

import "./knowledge-page.css";

export function KnowledgeDocumentsPage() {
  const tenantId = useTenantId();
  const { spaceId } = useParams();
  const navigate = useNavigate();
  const auth = useAuth();
  const client = useQueryClient();
  const spaces = useQuery({
    queryKey: ["admin", tenantId, "knowledge-spaces"],
    queryFn: () => adminApi.listKnowledgeSpaces(tenantId ?? ""),
    enabled: Boolean(tenantId),
  });
  const space = (spaces.data ?? []).find((item) => item.id === spaceId);

  if (!tenantId) return <TenantRequiredState />;

  const breadcrumbs = (
    <Breadcrumb
      className="knowledge-documents-breadcrumbs"
      items={[
        { title: <Link to="/admin">工作台</Link> },
        { title: <Link to="/admin/knowledge">知识库</Link> },
        { title: "文档" },
      ]}
    />
  );

  if (spaces.isPending) {
    return (
      <section className="knowledge-page">
        {breadcrumbs}
        <p role="status">正在加载知识库…</p>
      </section>
    );
  }
  if (spaces.isError) {
    return (
      <section className="knowledge-page">
        {breadcrumbs}
        <RequestErrorAlert error={spaces.error} fallback="加载知识库失败" />
      </section>
    );
  }
  if (!space) {
    return (
      <section className="knowledge-page">
        {breadcrumbs}
        <Alert showIcon type="info" message="知识库不存在，或当前账号没有查看权限。" />
      </section>
    );
  }

  return (
    <section className="knowledge-page">
      {breadcrumbs}
      <KnowledgeDocumentsPanel
        tenantId={tenantId}
        space={space}
        canRead={auth.hasPermission("knowledge.documents.read")}
        canManage={auth.hasPermission("knowledge.documents.manage")}
        canConfigure={auth.hasPermission("knowledge.spaces.manage")}
        canQuery={auth.hasPermission("knowledge.query")}
        onOpenSearch={() => void navigate(`/admin/knowledge/${space.id}/retrieval`)}
        onOpenDocument={(document) =>
          void navigate(`/admin/knowledge/${space.id}/documents/${document.id}`)
        }
        onSpaceUpdated={(updated) => {
          client.setQueryData<KnowledgeSpace[]>(
            ["admin", tenantId, "knowledge-spaces"],
            (current) => current?.map((item) => (item.id === updated.id ? updated : item)),
          );
        }}
      />
    </section>
  );
}
