import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { App, Alert, Button, Form, Input, Modal, Progress, Tabs, Upload } from "antd";
import type { UploadProps } from "antd";

import {
  type BatchFileUploadItem,
  KnowledgeBatchUploadItem,
} from "@/features/admin/KnowledgeBatchUploadItem";
import {
  knowledgeDocumentTitleFromFile,
  knowledgeUploadAccept,
  knowledgeUploadContentType,
} from "@/features/admin/knowledgeUpload";
import { uploadKnowledgeDocument } from "@/features/admin/uploadKnowledgeDocument";
import type { KnowledgeDocumentCreate, KnowledgeIngestion } from "@/shared/api/types";
import { toUserErrorMessage } from "@/shared/http";
import { AppIcon } from "@/shared/icons";
import { RequestErrorAlert } from "@/shared/ui";

const MAX_BATCH_FILES = 20;
const MAX_CONCURRENT_UPLOADS = 3;
const TEXT_ENTRY_FORM_ID = "knowledge-text-entry-form";

type Props = {
  tenantId: string;
  spaceId: string;
  open: boolean;
  onClose: () => void;
  onQueued: (job: KnowledgeIngestion, title: string) => void;
  onSourceIssued?: (sourceId: string) => void;
  textEntry?: {
    error: Error | null;
    loading: boolean;
    onCreate: (payload: KnowledgeDocumentCreate) => Promise<unknown>;
  };
};

export function KnowledgeBatchUploadModal({
  tenantId,
  spaceId,
  open,
  onClose,
  onQueued,
  onSourceIssued,
  textEntry,
}: Props) {
  const [activeTab, setActiveTab] = useState("upload");
  const [items, setItems] = useState<BatchFileUploadItem[]>([]);
  const { message } = App.useApp();
  const upload = useMutation({
    mutationFn: (targets: BatchFileUploadItem[]) =>
      runWithConcurrency(targets, MAX_CONCURRENT_UPLOADS, async (target) => {
        updateItem(setItems, target.id, { status: "uploading", percent: 0, error: undefined });
        try {
          const job = await uploadKnowledgeDocument({
            tenantId,
            spaceId,
            file: target.file,
            title: target.title,
            onProgress: (percent) => updateItem(setItems, target.id, { percent }),
            onSourceIssued,
          });
          updateItem(setItems, target.id, { status: "queued", percent: 100 });
          onQueued(job, target.title.trim());
          return true;
        } catch (error) {
          updateItem(setItems, target.id, {
            status: "failed",
            error: toUserErrorMessage(error, "上传失败，请稍后重试。"),
          });
          return false;
        }
      }),
    onSuccess: (results) => {
      if (results.every(Boolean)) resetAndClose();
      else
        void message.error(
          `${results.filter((result) => !result).length} 个文件上传失败，可直接重试失败项。`,
        );
    },
  });
  const pendingItems = items.filter(
    (item) => item.status === "selected" || item.status === "failed",
  );
  const overallPercent = useMemo(() => batchProgress(items), [items]);
  const hasBlankTitle = pendingItems.some((item) => !item.title.trim());
  const failedCount = items.filter((item) => item.status === "failed").length;
  const modalState = createModalState({
    activeTab,
    failedCount,
    hasBlankTitle,
    hasPendingRequest: upload.isPending || Boolean(textEntry?.loading),
    pendingItemCount: pendingItems.length,
    textEntry,
    uploadPending: upload.isPending,
  });

  const beforeUpload: UploadProps["beforeUpload"] = (file) => {
    if (!knowledgeUploadContentType(file.name)) {
      void message.error("已忽略不支持的文件；当前仅支持 PDF、DOCX、MD 和 TXT 文件。");
      return Upload.LIST_IGNORE;
    }
    setItems((current) => {
      const id = fileIdentity(file);
      if (current.some((item) => item.id === id) || current.length >= MAX_BATCH_FILES)
        return current;
      return [
        ...current,
        {
          id,
          file,
          title: knowledgeDocumentTitleFromFile(file.name),
          percent: 0,
          status: "selected",
        },
      ];
    });
    return Upload.LIST_IGNORE;
  };
  const submit = () => {
    if (!pendingItems.length || hasBlankTitle) return;
    upload.mutate(pendingItems);
  };
  const resetAndClose = () => {
    setItems([]);
    setActiveTab("upload");
    upload.reset();
    onClose();
  };

  return (
    <Modal
      title={textEntry ? "添加文档" : "批量上传知识文件"}
      open={open}
      width={720}
      destroyOnHidden
      closable={!modalState.pending}
      confirmLoading={modalState.pending}
      cancelButtonProps={{ disabled: modalState.pending }}
      maskClosable={!modalState.pending}
      okButtonProps={{
        disabled: modalState.submitDisabled,
        form: modalState.isTextEntry ? TEXT_ENTRY_FORM_ID : undefined,
        htmlType: modalState.isTextEntry ? "submit" : "button",
      }}
      okText={modalState.submitLabel}
      onCancel={resetAndClose}
      onOk={modalState.isTextEntry ? undefined : submit}
    >
      {textEntry ? (
        <Tabs
          activeKey={activeTab}
          items={[
            {
              key: "upload",
              label: "上传文件",
              children: uploadContent(),
              disabled: modalState.hasPendingRequest,
            },
            {
              key: "text",
              label: "录入文本",
              children: textContent(),
              disabled: modalState.hasPendingRequest,
            },
          ]}
          onChange={setActiveTab}
        />
      ) : (
        uploadContent()
      )}
    </Modal>
  );

  function uploadContent() {
    return (
      <>
        <Alert
          showIcon
          type="info"
          message={`一次最多选择 ${MAX_BATCH_FILES} 个 PDF、DOCX、MD 或 TXT 文件；最多 ${MAX_CONCURRENT_UPLOADS} 个并发上传。上传完成后会异步提取和切分。`}
        />
        <div className="knowledge-batch-picker">
          <Upload
            accept={knowledgeUploadAccept}
            beforeUpload={beforeUpload}
            disabled={upload.isPending || items.length >= MAX_BATCH_FILES}
            maxCount={MAX_BATCH_FILES}
            multiple
            showUploadList={false}
          >
            <Button icon={<AppIcon name="Upload" size="md" />}>
              {items.length ? "继续添加文件" : "选择多个文件"}
            </Button>
          </Upload>
          <span>
            {items.length}/{MAX_BATCH_FILES} 个文件
          </span>
        </div>
        {items.length ? (
          <>
            {upload.isPending ? (
              <Progress
                aria-label="批量上传总体进度"
                percent={overallPercent}
                size="small"
                status={failedCount ? "exception" : "active"}
              />
            ) : null}
            <div className="knowledge-batch-list">
              {items.map((item) => (
                <KnowledgeBatchUploadItem
                  item={item}
                  key={item.id}
                  uploading={upload.isPending}
                  onChange={(patch) => updateItem(setItems, item.id, patch)}
                  onRemove={() =>
                    setItems((current) => current.filter((entry) => entry.id !== item.id))
                  }
                />
              ))}
            </div>
          </>
        ) : (
          <div className="knowledge-batch-empty">尚未选择文件</div>
        )}
      </>
    );
  }

  function textContent() {
    return (
      <>
        <RequestErrorAlert error={textEntry?.error ?? null} fallback="创建知识文档失败" />
        <Form
          className="admin-modal-form"
          id={TEXT_ENTRY_FORM_ID}
          layout="vertical"
          onFinish={(payload: KnowledgeDocumentCreate) => {
            if (!textEntry) return;
            void textEntry
              .onCreate(payload)
              .then(resetAndClose)
              .catch(() => undefined);
          }}
        >
          <Form.Item name="title" label="标题" rules={[{ required: true, whitespace: true }]}>
            <Input placeholder="例如：产品发布流程" />
          </Form.Item>
          <Form.Item name="source_uri" label="来源链接（可选）" rules={[{ type: "url" }]}>
            <Input placeholder="https://example.com/source" />
          </Form.Item>
          <Form.Item
            className="admin-form-item-wide"
            name="content"
            label="内容"
            rules={[{ required: true, whitespace: true }]}
          >
            <Input.TextArea rows={12} placeholder="输入需要供 Agent 检索的知识内容" />
          </Form.Item>
        </Form>
      </>
    );
  }
}

function createModalState({
  activeTab,
  failedCount,
  hasBlankTitle,
  hasPendingRequest,
  pendingItemCount,
  textEntry,
  uploadPending,
}: {
  activeTab: string;
  failedCount: number;
  hasBlankTitle: boolean;
  hasPendingRequest: boolean;
  pendingItemCount: number;
  textEntry: Props["textEntry"];
  uploadPending: boolean;
}) {
  const isTextEntry = activeTab === "text";
  const pending = isTextEntry ? Boolean(textEntry?.loading) : uploadPending;
  const submitDisabled = isTextEntry ? false : !pendingItemCount || hasBlankTitle;
  const submitLabel = isTextEntry
    ? "创建文档"
    : failedCount
      ? `重试 ${failedCount} 个失败文件`
      : `上传 ${pendingItemCount} 个文件`;
  return { hasPendingRequest, isTextEntry, pending, submitDisabled, submitLabel };
}

function updateItem(
  setItems: React.Dispatch<React.SetStateAction<BatchFileUploadItem[]>>,
  id: string,
  patch: Partial<BatchFileUploadItem>,
) {
  setItems((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));
}

function fileIdentity(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function batchProgress(items: BatchFileUploadItem[]) {
  if (!items.length) return 0;
  return Math.round(items.reduce((total, item) => total + item.percent, 0) / items.length);
}

async function runWithConcurrency<T, R>(
  values: T[],
  concurrency: number,
  task: (value: T) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(values.length);
  let cursor = 0;
  const worker = async () => {
    while (cursor < values.length) {
      const index = cursor;
      cursor += 1;
      results[index] = await task(values[index]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(concurrency, values.length) }, worker));
  return results;
}
