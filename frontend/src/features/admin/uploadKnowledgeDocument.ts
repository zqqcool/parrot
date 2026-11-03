import { knowledgeUploadContentType } from "@/features/admin/knowledgeUpload";
import { adminApi } from "@/shared/api/client";
import type { KnowledgeDocument, KnowledgeIngestion } from "@/shared/api/types";
import { uploadObject } from "@/shared/uploads";

type Options = {
  tenantId: string;
  spaceId: string;
  document?: KnowledgeDocument;
  file: File;
  title?: string;
  onProgress?: (percent: number) => void;
  onSourceIssued?: (sourceId: string) => void;
};

export async function uploadKnowledgeDocument({
  tenantId,
  spaceId,
  document,
  file,
  title,
  onProgress,
  onSourceIssued,
}: Options): Promise<KnowledgeIngestion> {
  const contentType = knowledgeUploadContentType(file.name);
  if (!contentType) throw new Error("当前仅支持 PDF、DOCX、MD 和 TXT 文件");

  if (!document && !title?.trim()) throw new Error("请填写文档标题");

  let sourceId = "";
  const stored = await uploadObject({
    file,
    contentType,
    onProgress,
    requestGrant: async (metadata) => {
      const uploadMetadata = { filename: file.name, ...metadata };
      const grant = document
        ? await adminApi.issueKnowledgeDocumentVersionUpload(tenantId, document.id, uploadMetadata)
        : await adminApi.issueKnowledgeDocumentUpload(tenantId, spaceId, {
            title: title!.trim(),
            ...uploadMetadata,
          });
      sourceId = grant.source_id;
      onSourceIssued?.(sourceId);
      return grant;
    },
  });
  return adminApi.confirmKnowledgeDocumentUpload(tenantId, sourceId, {
    staging_key: stored.object_key,
  });
}
