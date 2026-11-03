import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import { Alert, Breadcrumb, Result } from "antd";
import { Link, useParams } from "react-router-dom";

import { KnowledgeDocumentChunkList } from "@/features/admin/KnowledgeDocumentChunkList";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import type { KnowledgeDocument } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";

import "./knowledge-page.css";

export function KnowledgeDocumentDetailPage() {
  const tenantId = useTenantId();
  const { documentId, spaceId } = useParams();
  const auth = useAuth();
  const canRead = auth.hasPermission("knowledge.documents.read");
  const documents = useQuery({
    queryKey: ["admin", tenantId, "knowledge-spaces", spaceId, "documents", ""],
    queryFn: () => adminApi.listKnowledgeDocuments(tenantId ?? "", spaceId ?? ""),
    enabled: Boolean(tenantId && spaceId) && canRead,
  });

  if (!tenantId) return <TenantRequiredState />;
  if (!canRead) {
    return <Alert showIcon type="info" message="当前账号没有查看知识文档正文的权限。" />;
  }

  return (
    <section className="knowledge-page">
      <DocumentBreadcrumbs spaceId={spaceId} />
      <DocumentDetailState documentId={documentId} documents={documents} tenantId={tenantId} />
    </section>
  );
}

type DetailStateProps = {
  documentId: string | undefined;
  documents: UseQueryResult<KnowledgeDocument[], Error>;
  tenantId: string;
};

function DocumentDetailState({ documentId, documents, tenantId }: DetailStateProps) {
  if (documents.isPending) return <p role="status">正在加载文档…</p>;
  if (documents.isError) {
    return <Result status="error" title="知识文档暂不可用" />;
  }
  const document = documents.data?.find((item) => item.id === documentId);
  if (!document) {
    return <Alert showIcon type="info" message="文档不存在，或当前账号没有查看权限。" />;
  }
  return <KnowledgeDocumentChunkList document={document} tenantId={tenantId} />;
}

function DocumentBreadcrumbs({ spaceId }: { spaceId: string | undefined }) {
  return (
    <Breadcrumb
      className="knowledge-documents-breadcrumbs"
      items={[
        { title: <Link to="/admin">工作台</Link> },
        { title: <Link to="/admin/knowledge">知识库</Link> },
        { title: <Link to={`/admin/knowledge/${spaceId ?? ""}/documents`}>文档</Link> },
        { title: "分段正文" },
      ]}
    />
  );
}
