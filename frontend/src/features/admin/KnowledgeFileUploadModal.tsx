import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { App, Button, Form, Input, Modal, Progress, Tabs, Typography, Upload } from "antd";
import type { UploadFile, UploadProps } from "antd";

import { KnowledgeBatchUploadModal } from "@/features/admin/KnowledgeBatchUploadModal";
import {
  knowledgeUploadAccept,
  knowledgeUploadContentType,
} from "@/features/admin/knowledgeUpload";
import { uploadKnowledgeDocument } from "@/features/admin/uploadKnowledgeDocument";
import type {
  KnowledgeDocument,
  KnowledgeDocumentCreate,
  KnowledgeIngestion,
} from "@/shared/api/types";
import { adminApi } from "@/shared/api/client";
import { AppIcon } from "@/shared/icons";
import { RequestErrorAlert } from "@/shared/ui";

type Props = {
  tenantId: string;
  spaceId: string;
  document?: KnowledgeDocument;
  open: boolean;
  onClose: () => void;
  onCreate?: (payload: KnowledgeDocumentCreate) => Promise<unknown>;
  onQueued: (job: KnowledgeIngestion, title: string) => void;
  onSourceIssued?: (sourceId: string) => void;
  onTextReplaced?: () => Promise<void>;
  textCreateError?: Error | null;
  textCreatePending?: boolean;
};

export function KnowledgeFileUploadModal({
  tenantId,
  spaceId,
  document,
  open,
  onClose,
  onCreate,
  onQueued,
  onSourceIssued,
  onTextReplaced,
  textCreateError,
  textCreatePending,
}: Props) {
  if (!document) {
    return (
      <KnowledgeBatchUploadModal
        tenantId={tenantId}
        spaceId={spaceId}
        open={open}
        onClose={onClose}
        onQueued={onQueued}
        onSourceIssued={onSourceIssued}
        textEntry={
          onCreate
            ? {
                error: textCreateError ?? null,
                loading: Boolean(textCreatePending),
                onCreate,
              }
            : undefined
        }
      />
    );
  }
  return (
    <KnowledgeReplacementUploadModal
      tenantId={tenantId}
      spaceId={spaceId}
      document={document}
      open={open}
      onClose={onClose}
      onQueued={onQueued}
      onSourceIssued={onSourceIssued}
      onTextReplaced={onTextReplaced}
    />
  );
}

function KnowledgeReplacementUploadModal({
  tenantId,
  spaceId,
  document,
  open,
  onClose,
  onQueued,
  onSourceIssued,
  onTextReplaced,
}: Props & { document: KnowledgeDocument }) {
  const [activeTab, setActiveTab] = useState("file");
  const [textForm] = Form.useForm<{ content: string }>();
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const { message } = App.useApp();
  const upload = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("请选择要上传的文件");
      return uploadKnowledgeDocument({
        tenantId,
        spaceId,
        document,
        file,
        onProgress: setProgress,
        onSourceIssued,
      });
    },
    onSuccess: (job) => {
      onQueued(job, document.title);
      resetAndClose();
    },
  });
  const textUpdate = useMutation({
    mutationFn: (payload: { content: string }) =>
      adminApi.createKnowledgeDocumentTextVersion(tenantId, document.id, payload),
    onSuccess: async () => {
      await onTextReplaced?.();
      resetAndClose();
    },
  });
  const isTextUpdate = activeTab === "text";
  const isPending = upload.isPending || textUpdate.isPending;

  const beforeUpload: UploadProps["beforeUpload"] = (selected) => {
    if (!knowledgeUploadContentType(selected.name)) {
      setFile(null);
      void message.error("当前仅支持 PDF、DOCX、MD 和 TXT 文件；图片需要 OCR 能力后才可上传。");
      return Upload.LIST_IGNORE;
    }
    setFile(selected);
    return false;
  };
  const submit = () => {
    if (!file) {
      void message.error("请选择要上传的文件");
      return;
    }
    upload.mutate();
  };
  const submitText = () => {
    void textForm
      .validateFields()
      .then(textUpdate.mutate)
      .catch(() => undefined);
  };
  const resetAndClose = () => {
    setActiveTab("file");
    setFile(null);
    setProgress(0);
    textForm.resetFields();
    upload.reset();
    textUpdate.reset();
    onClose();
  };
  const fileList: UploadFile[] = file
    ? [{ uid: "knowledge-upload", name: file.name, status: "done" }]
    : [];

  return (
    <Modal
      title="上传新版本"
      open={open}
      destroyOnHidden
      closable={!isPending}
      confirmLoading={isPending}
      cancelButtonProps={{ disabled: isPending }}
      maskClosable={!isPending}
      okButtonProps={{ disabled: isTextUpdate ? false : !file }}
      okText={isTextUpdate ? "发布新版本" : "开始上传"}
      width={640}
      onCancel={resetAndClose}
      onOk={isTextUpdate ? submitText : submit}
    >
      <Typography.Paragraph type="secondary">
        为“{document.title}”创建新版本，文档标题保持不变。
      </Typography.Paragraph>
      <Tabs
        activeKey={activeTab}
        tabBarGutter={28}
        items={[
          {
            key: "file",
            label: "上传文件",
            children: fileContent(),
            disabled: isPending,
          },
          {
            key: "text",
            label: "录入文本",
            children: textContent(),
            disabled: isPending,
            forceRender: true,
          },
        ]}
        onChange={setActiveTab}
      />
    </Modal>
  );

  function fileContent() {
    return (
      <>
        <RequestErrorAlert error={upload.error} fallback="上传知识文件失败" />
        <Typography.Paragraph type="secondary">
          新文件会在后台提取和切分；发布成功前，当前版本会继续参与检索。
        </Typography.Paragraph>
        <Form layout="vertical" requiredMark={false}>
          <Form.Item label="选择新版本文件" extra="支持 PDF、DOCX、MD、TXT 格式。">
            <Upload
              accept={knowledgeUploadAccept}
              beforeUpload={beforeUpload}
              disabled={isPending}
              fileList={fileList}
              maxCount={1}
              onChange={({ fileList: nextFiles }) => {
                if (!nextFiles.length) setFile(null);
              }}
              onRemove={() => {
                setFile(null);
                return true;
              }}
            >
              <Button icon={<AppIcon name="Upload" size="md" />}>
                {file ? "重新选择文件" : "选择文件"}
              </Button>
            </Upload>
          </Form.Item>
        </Form>
        {upload.isPending ? (
          <Progress aria-label="文件上传进度" percent={Math.round(progress)} status="active" />
        ) : null}
      </>
    );
  }

  function textContent() {
    return (
      <>
        <RequestErrorAlert error={textUpdate.error} fallback="发布文本新版本失败" />
        <Typography.Paragraph type="secondary">
          发布后会立即生成不可变的新版本，旧版本停止检索，索引随后更新。
        </Typography.Paragraph>
        <Form form={textForm} layout="vertical" requiredMark={false}>
          <Form.Item
            name="content"
            label="新版本内容"
            rules={[{ required: true, whitespace: true }]}
          >
            <Input.TextArea rows={12} placeholder="输入替换当前文档版本的文本内容" />
          </Form.Item>
        </Form>
      </>
    );
  }
}
