import { Button, Popconfirm, Space } from "antd";

import type { KnowledgeDocument } from "@/shared/api/types";

type Props = {
  document: KnowledgeDocument;
  canManage: boolean;
  archivingDocumentId: string | null;
  downloadingDocumentId: string | null;
  onArchive: (document: KnowledgeDocument) => void;
  onDownload: (document: KnowledgeDocument) => void;
  onView: (document: KnowledgeDocument) => void;
  onReplace: (document: KnowledgeDocument) => void;
};

export function KnowledgeDocumentActions({
  document,
  canManage,
  archivingDocumentId,
  downloadingDocumentId,
  onArchive,
  onDownload,
  onView,
  onReplace,
}: Props) {
  return (
    <Space size={2}>
      <Button size="small" type="link" onClick={() => onView(document)}>
        查看
      </Button>
      <Button
        loading={downloadingDocumentId === document.id}
        size="small"
        type="link"
        onClick={() => onDownload(document)}
      >
        下载源文件
      </Button>
      {canManage ? (
        <Button
          disabled={document.status !== "active"}
          size="small"
          type="link"
          onClick={() => onReplace(document)}
        >
          上传新版本
        </Button>
      ) : null}
      {canManage ? (
        <Popconfirm
          cancelText="取消"
          okText="确认归档"
          title="确认归档该知识文档？"
          description="归档后会立即停止被已绑定 Agent 检索。"
          onConfirm={() => onArchive(document)}
        >
          <Button
            danger
            disabled={document.status !== "active"}
            loading={archivingDocumentId === document.id}
            size="small"
            type="link"
          >
            归档
          </Button>
        </Popconfirm>
      ) : null}
    </Space>
  );
}
