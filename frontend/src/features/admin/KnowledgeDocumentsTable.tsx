import { Space, Tag, Tooltip } from "antd";

import { KnowledgeDocumentActions } from "@/features/admin/KnowledgeDocumentActions";
import { KnowledgeStagingSourceActions } from "@/features/admin/KnowledgeStagingSourceActions";
import type { KnowledgeDocument, KnowledgeSourceActivity } from "@/shared/api/types";
import { formatDateTime } from "@/shared/time";
import { DataTable, UserIdentity } from "@/shared/ui";

type Props = {
  archivingDocumentId: string | null;
  canManage: boolean;
  documents: KnowledgeDocument[];
  downloadingDocumentId: string | null;
  loading: boolean;
  pendingStagingSourceId: string | null;
  tenantId: string;
  sources?: KnowledgeSourceActivity[];
  resetPaginationKey?: string;
  onArchive: (document: KnowledgeDocument) => void;
  onDownload: (document: KnowledgeDocument) => void;
  onView: (document: KnowledgeDocument) => void;
  onReplace: (document: KnowledgeDocument) => void;
  onCleanupStagingSource: (source: KnowledgeSourceActivity) => Promise<void>;
  onRetryStagingConfirmation: (source: KnowledgeSourceActivity) => Promise<void>;
};

type DocumentRow = {
  id: string;
  kind: "document";
  document: KnowledgeDocument;
  source: KnowledgeSourceActivity | null;
  updatedAt: string;
};

type UploadRow = {
  id: string;
  kind: "upload";
  source: KnowledgeSourceActivity;
  updatedAt: string;
};

type KnowledgeRow = DocumentRow | UploadRow;

export function KnowledgeDocumentsTable(props: Props) {
  const rows = mergeDocumentRows(props.documents, props.sources ?? []);

  return (
    <DataTable<KnowledgeRow>
      rowKey="id"
      loading={props.loading}
      dataSource={rows}
      resetPaginationKey={props.resetPaginationKey}
      locale={{ emptyText: "当前知识库暂无文档" }}
      columns={[
        {
          title: "标题",
          width: 260,
          ellipsis: { showTitle: false },
          render: rowTitle,
        },
        { title: "版本", width: 82, render: rowVersion },
        { title: "分块", width: 82, render: rowChunkCount },
        { title: "更新时间", width: 180, render: rowUpdatedAt },
        { title: "来源", ellipsis: true, render: rowSource },
        {
          title: "变更人",
          width: 150,
          render: (_: unknown, row: KnowledgeRow) => rowChangedBy(props.tenantId, row),
        },
        { title: "处理状态", width: 220, render: rowStatus },
        {
          title: "操作",
          width: props.canManage ? 410 : 160,
          render: (_: unknown, row: KnowledgeRow) =>
            row.kind === "document" ? (
              <Space size={8} wrap>
                <KnowledgeDocumentActions
                  archivingDocumentId={props.archivingDocumentId}
                  canManage={props.canManage}
                  document={row.document}
                  downloadingDocumentId={props.downloadingDocumentId}
                  onArchive={props.onArchive}
                  onDownload={props.onDownload}
                  onView={props.onView}
                  onReplace={props.onReplace}
                />
                {props.canManage && row.source ? (
                  <KnowledgeStagingSourceActions
                    pendingSourceId={props.pendingStagingSourceId}
                    source={row.source}
                    onCleanup={props.onCleanupStagingSource}
                    onRetryConfirmation={props.onRetryStagingConfirmation}
                  />
                ) : null}
              </Space>
            ) : props.canManage ? (
              <KnowledgeStagingSourceActions
                pendingSourceId={props.pendingStagingSourceId}
                source={row.source}
                onCleanup={props.onCleanupStagingSource}
                onRetryConfirmation={props.onRetryStagingConfirmation}
              />
            ) : (
              "-"
            ),
        },
      ]}
    />
  );
}

function mergeDocumentRows(
  documents: KnowledgeDocument[],
  sources: KnowledgeSourceActivity[],
): KnowledgeRow[] {
  const latestPendingSourceByDocumentId = new Map<string, KnowledgeSourceActivity>();
  const unconfirmedUploads: KnowledgeSourceActivity[] = [];

  for (const source of sources) {
    if (source.status === "completed") continue;
    if (source.document_id) {
      const current = latestPendingSourceByDocumentId.get(source.document_id);
      if (!current || Date.parse(source.updated_at) > Date.parse(current.updated_at)) {
        latestPendingSourceByDocumentId.set(source.document_id, source);
      }
      continue;
    }
    unconfirmedUploads.push(source);
  }

  const documentRows: DocumentRow[] = documents.map((document) => ({
    id: document.id,
    kind: "document",
    document,
    source: latestPendingSourceByDocumentId.get(document.id) ?? null,
    updatedAt: document.updated_at,
  }));
  const uploadRows: UploadRow[] = unconfirmedUploads.map((source) => ({
    id: source.id,
    kind: "upload",
    source,
    updatedAt: source.updated_at,
  }));

  return [...documentRows, ...uploadRows].sort(
    (left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt),
  );
}

function rowTitle(_: unknown, row: KnowledgeRow) {
  const title = row.kind === "document" ? row.document.title : row.source.original_filename;
  return (
    <Tooltip placement="topLeft" title={title}>
      <span>{title}</span>
    </Tooltip>
  );
}

function rowVersion(_: unknown, row: KnowledgeRow) {
  return row.kind === "document" ? row.document.current_version : "-";
}

function rowChunkCount(_: unknown, row: KnowledgeRow) {
  return row.kind === "document" ? row.document.chunk_count : "-";
}

function rowUpdatedAt(_: unknown, row: KnowledgeRow) {
  return formatDateTime(row.updatedAt);
}

function rowSource(_: unknown, row: KnowledgeRow) {
  if (row.kind === "upload") return "上传文件";
  const sourceUri = row.document.source_uri;
  return sourceUri ? <span title={sourceUri}>{sourceUri}</span> : "-";
}

function rowChangedBy(tenantId: string, row: KnowledgeRow) {
  const user = row.kind === "document" ? row.document.changed_by_user : row.source.created_by_user;
  const unknownLabel =
    row.kind === "document"
      ? row.document.changed_by_display_name
      : row.source.created_by_display_name;
  return <UserIdentity tenantId={tenantId} unknownLabel={unknownLabel} user={user} />;
}

function rowStatus(_: unknown, row: KnowledgeRow) {
  const source = row.source;
  const status =
    source && source.status !== "completed" ? sourceStatus(source) : documentStatus(row);
  return (
    <span className="knowledge-document-status">
      <Tag color={status.color}>{status.label}</Tag>
      <span className="knowledge-document-status-description">{status.description}</span>
    </span>
  );
}

function documentStatus(row: KnowledgeRow) {
  if (row.kind !== "document") return { color: "default", label: "未知", description: "状态未知" };
  if (row.document.status === "active") {
    return { color: "success", label: "启用", description: "文档已生成" };
  }
  if (row.document.status === "processing") {
    return { color: "processing", label: "处理中", description: "正在解析文档" };
  }
  if (row.document.status === "failed") {
    return { color: "error", label: "处理失败", description: "文档未能生成" };
  }
  return { color: "default", label: "已归档", description: "文档已归档" };
}

function sourceStatus(source: KnowledgeSourceActivity) {
  const isReplacement = source.change_kind === "replace";
  if (source.status === "staging") {
    return {
      color: "warning",
      label: isReplacement ? "待确认更新" : "待确认",
      description: stagingDescription(source, isReplacement),
    };
  }
  if (source.status === "queued") {
    return {
      color: "processing",
      label: isReplacement ? "更新排队中" : "排队中",
      description: "等待后台处理",
    };
  }
  if (source.status === "processing") {
    return {
      color: "processing",
      label: isReplacement ? "更新处理中" : "处理中",
      description: "正在提取内容并生成分块",
    };
  }
  return {
    color: "error",
    label: isReplacement ? "更新失败" : "处理失败",
    description: source.error_code ? `错误码：${source.error_code}` : "后台处理未完成",
  };
}

function stagingDescription(source: KnowledgeSourceActivity, isReplacement: boolean) {
  const prefix = isReplacement ? "新版本尚未完成上传确认" : "尚未完成上传确认";
  return source.staging_expires_at
    ? `${prefix}，将在 ${formatDateTime(source.staging_expires_at)} 自动清理`
    : prefix;
}
