import { Alert, Button, Space } from "antd";

import { CreateKnowledgeDocumentModal } from "@/features/admin/KnowledgeModals";
import { KnowledgeFileUploadModal } from "@/features/admin/KnowledgeFileUploadModal";
import { KnowledgeIngestionNotice } from "@/features/admin/KnowledgeIngestionNotice";
import { useKnowledgeDocuments } from "@/features/admin/useKnowledgeDocuments";
import type { KnowledgeSpace } from "@/shared/api/types";

type Props = {
  canManageDocuments: boolean;
  canReadDocuments: boolean;
  space: KnowledgeSpace;
  tenantId: string;
  onComplete: () => void;
};

export function KnowledgeSpaceUploadStep({
  canManageDocuments,
  canReadDocuments,
  space,
  tenantId,
  onComplete,
}: Props) {
  const documents = useKnowledgeDocuments({
    tenantId,
    spaceId: space.id,
    canRead: canReadDocuments,
    query: "",
  });

  return (
    <section className="knowledge-create-upload" aria-labelledby="knowledge-upload-step-heading">
      <div>
        <h2 id="knowledge-upload-step-heading">上传资料</h2>
        <p>
          为“{space.name}”添加 PDF、DOCX、MD 或 TXT 文件，也可以直接录入文本。文件会异步提取、分块并发布。
        </p>
      </div>
      {canManageDocuments ? (
        <>
          <Space wrap>
            <Button type="primary" onClick={() => documents.setUploading(true)}>
              上传文件
            </Button>
            <Button onClick={() => documents.setCreating(true)}>录入文本</Button>
          </Space>
          <Alert
            showIcon
            type="info"
            message="资料处理完成前，Agent 不会检索新上传或录入的内容。"
          />
          <KnowledgeIngestionNotice
            items={documents.ingestionItems}
            onDismiss={documents.dismissIngestions}
          />
        </>
      ) : (
        <Alert
          showIcon
          type="warning"
          message="知识库已创建，但当前账号没有管理文档的权限；请联系拥有知识文档管理权限的成员上传资料。"
        />
      )}
      <div className="knowledge-create-upload-actions">
        <Button onClick={onComplete}>完成，进入文档区</Button>
      </div>
      <CreateKnowledgeDocumentModal
        open={documents.creating}
        loading={documents.create.isPending}
        error={documents.create.error}
        onCancel={() => documents.setCreating(false)}
        onSubmit={documents.create.mutate}
      />
      <KnowledgeFileUploadModal
        tenantId={tenantId}
        spaceId={space.id}
        open={documents.uploading}
        onClose={() => documents.setUploading(false)}
        onQueued={documents.queueIngestion}
      />
    </section>
  );
}
