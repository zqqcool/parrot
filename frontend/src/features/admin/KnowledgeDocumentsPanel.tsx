import { useState } from "react";
import { Alert } from "antd";

import { KnowledgeDocumentsHeading } from "@/features/admin/KnowledgeDocumentsHeading";
import { KnowledgeDocumentsTable } from "@/features/admin/KnowledgeDocumentsTable";
import { KnowledgeFileUploadModal } from "@/features/admin/KnowledgeFileUploadModal";
import { KnowledgeIngestionNotice } from "@/features/admin/KnowledgeIngestionNotice";
import { KnowledgeChunkingSettings } from "@/features/admin/KnowledgeChunkingSettings";
import {
  type IngestionQueueItem,
  useKnowledgeDocuments,
} from "@/features/admin/useKnowledgeDocuments";
import { useKnowledgeSourceActivity } from "@/features/admin/useKnowledgeSourceActivity";
import type {
  KnowledgeDocument,
  KnowledgeDocumentCreate,
  KnowledgeIngestion,
  KnowledgeSourceActivity,
  KnowledgeSpace,
} from "@/shared/api/types";
import { RequestErrorAlert, SearchBar, useDebouncedValue } from "@/shared/ui";

type Props = {
  tenantId: string;
  space: KnowledgeSpace | null;
  canRead: boolean;
  canManage: boolean;
  canConfigure: boolean;
  onSpaceUpdated: (space: KnowledgeSpace) => void;
  onOpenSearch: () => void;
  onOpenDocument: (document: KnowledgeDocument) => void;
  canQuery: boolean;
};

export function KnowledgeDocumentsPanel({
  tenantId,
  space,
  canRead,
  canManage,
  canConfigure,
  canQuery,
  onOpenSearch,
  onOpenDocument,
  onSpaceUpdated,
}: Props) {
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const state = useKnowledgeDocuments({
    tenantId,
    spaceId: space?.id,
    canRead,
    query: searchQuery,
  });
  const sourceActivity = useKnowledgeSourceActivity({
    tenantId,
    spaceId: space?.id,
    canRead,
  });

  if (!space) {
    return (
      <Alert
        showIcon
        type="info"
        message="先创建或选择一个知识库，再进入文档区上传文件或录入文本。"
      />
    );
  }
  if (!canRead) {
    return <Alert showIcon type="info" message="当前账号没有查看知识文档的权限。" />;
  }

  return (
    <KnowledgeDocumentsContent
      archiveError={state.archive.error}
      archivingDocumentId={state.archivingDocumentId}
      canConfigure={canConfigure}
      canManage={canManage}
      canQuery={canQuery}
      createError={state.create.error}
      createPending={state.create.isPending}
      documents={state.documents.data ?? []}
      documentsError={state.documents.error}
      documentsLoading={state.documents.isFetching || sourceActivity.query.isLoading}
      downloadError={state.download.error}
      downloadingDocumentId={state.downloadingDocumentId}
      ingestionItems={state.ingestionItems}
      sources={sourceActivity.query.data?.items ?? []}
      pendingStagingSourceId={sourceActivity.pendingSourceId}
      space={space}
      tenantId={tenantId}
      uploading={state.uploading}
      replacing={state.replacing}
      searchQuery={searchQuery}
      searchValue={searchValue}
      onArchive={state.archive.mutate}
      onCreate={state.create.mutateAsync}
      onDismissIngestion={state.dismissIngestions}
      onOpenAdd={() => state.setUploading(true)}
      onOpenSearch={onOpenSearch}
      onOpenDocument={onOpenDocument}
      onDownload={state.download.mutate}
      onReplace={state.setReplacing}
      onCleanupStagingSource={async (source) => {
        await sourceActivity.cleanupStagingSource.mutateAsync(source.id);
        await state.refreshDocuments();
      }}
      onRetryStagingConfirmation={async (source) => {
        try {
          const job = await sourceActivity.retryConfirmation.mutateAsync(source.id);
          state.queueIngestion(job, source.title);
          await state.refreshDocuments();
        } catch {
          await Promise.all([sourceActivity.refresh(), state.refreshDocuments()]);
        }
      }}
      onQueued={(job, title) => {
        state.queueIngestion(job, title);
        void sourceActivity.refresh();
      }}
      onSourceIssued={() => {
        void sourceActivity.refresh();
      }}
      onTextReplaced={async () => {
        state.setReplacing(null);
        await state.refreshDocuments();
      }}
      onSearchChange={setSearchValue}
      onSpaceUpdated={onSpaceUpdated}
      onCloseUpload={() => state.setUploading(false)}
      onCloseReplace={() => state.setReplacing(null)}
    />
  );
}

type DocumentsContentProps = {
  archiveError: Error | null;
  archivingDocumentId: string | null;
  canConfigure: boolean;
  canManage: boolean;
  canQuery: boolean;
  createError: Error | null;
  createPending: boolean;
  documents: KnowledgeDocument[];
  documentsError: Error | null;
  documentsLoading: boolean;
  downloadError: Error | null;
  downloadingDocumentId: string | null;
  ingestionItems: IngestionQueueItem[];
  pendingStagingSourceId: string | null;
  sources: KnowledgeSourceActivity[];
  space: KnowledgeSpace;
  tenantId: string;
  uploading: boolean;
  replacing: KnowledgeDocument | null;
  searchQuery: string;
  searchValue: string;
  onArchive: (document: KnowledgeDocument) => void;
  onCloseUpload: () => void;
  onCloseReplace: () => void;
  onCreate: (payload: KnowledgeDocumentCreate) => Promise<unknown>;
  onDismissIngestion: () => void;
  onDownload: (document: KnowledgeDocument) => void;
  onOpenAdd: () => void;
  onOpenSearch: () => void;
  onOpenDocument: (document: KnowledgeDocument) => void;
  onReplace: (document: KnowledgeDocument) => void;
  onCleanupStagingSource: (source: KnowledgeSourceActivity) => Promise<void>;
  onRetryStagingConfirmation: (source: KnowledgeSourceActivity) => Promise<void>;
  onQueued: (job: KnowledgeIngestion, title: string) => void;
  onSourceIssued: () => void;
  onTextReplaced: () => Promise<void>;
  onSearchChange: (value: string) => void;
  onSpaceUpdated: (space: KnowledgeSpace) => void;
};

function KnowledgeDocumentsContent(props: DocumentsContentProps) {
  return (
    <section className="knowledge-documents-panel" aria-labelledby="knowledge-documents-heading">
      <KnowledgeDocumentsHeading
        canManage={props.canManage}
        canQuery={props.canQuery}
        space={props.space}
        onOpenAdd={props.onOpenAdd}
        onOpenSearch={props.onOpenSearch}
      />
      <KnowledgeChunkingSettings
        canManage={props.canConfigure}
        space={props.space}
        tenantId={props.tenantId}
        onUpdated={props.onSpaceUpdated}
      />
      <KnowledgeIngestionNotice items={props.ingestionItems} onDismiss={props.onDismissIngestion} />
      <RequestErrorAlert error={props.documentsError} fallback="加载知识文档失败" />
      <SearchBar
        hasActiveFilters={Boolean(props.searchValue)}
        placeholder="搜索文档标题或来源"
        value={props.searchValue}
        onChange={props.onSearchChange}
        onReset={() => props.onSearchChange("")}
      />
      <KnowledgeDocumentsTable
        archivingDocumentId={props.archivingDocumentId}
        canManage={props.canManage}
        documents={props.documents}
        downloadingDocumentId={props.downloadingDocumentId}
        loading={props.documentsLoading}
        pendingStagingSourceId={props.pendingStagingSourceId}
        resetPaginationKey={props.searchQuery}
        sources={props.sources}
        tenantId={props.tenantId}
        onArchive={props.onArchive}
        onDownload={props.onDownload}
        onView={props.onOpenDocument}
        onReplace={props.onReplace}
        onCleanupStagingSource={props.onCleanupStagingSource}
        onRetryStagingConfirmation={props.onRetryStagingConfirmation}
      />
      <RequestErrorAlert error={props.archiveError} fallback="归档知识文档失败" />
      <RequestErrorAlert error={props.downloadError} fallback="下载知识源文件失败" />
      <KnowledgeFileUploadModal
        tenantId={props.tenantId}
        spaceId={props.space.id}
        open={props.uploading}
        textCreateError={props.createError}
        textCreatePending={props.createPending}
        onCreate={props.onCreate}
        onClose={props.onCloseUpload}
        onQueued={props.onQueued}
        onSourceIssued={props.onSourceIssued}
      />
      <KnowledgeFileUploadModal
        tenantId={props.tenantId}
        spaceId={props.space.id}
        document={props.replacing ?? undefined}
        open={Boolean(props.replacing)}
        onClose={props.onCloseReplace}
        onQueued={props.onQueued}
        onSourceIssued={props.onSourceIssued}
        onTextReplaced={props.onTextReplaced}
      />
    </section>
  );
}
