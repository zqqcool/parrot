import { Button, Input, Progress } from "antd";

import { AppIcon } from "@/shared/icons";

export type BatchFileUploadStatus = "selected" | "uploading" | "queued" | "failed";

export type BatchFileUploadItem = {
  id: string;
  file: File;
  title: string;
  percent: number;
  status: BatchFileUploadStatus;
  error?: string;
};

type Props = {
  item: BatchFileUploadItem;
  uploading: boolean;
  onChange: (patch: Partial<BatchFileUploadItem>) => void;
  onRemove: () => void;
};

export function KnowledgeBatchUploadItem({ item, uploading, onChange, onRemove }: Props) {
  const canEdit = !uploading && item.status !== "queued";
  return (
    <div className="knowledge-batch-item">
      <div className="knowledge-batch-item-heading">
        <span title={item.file.name}>{item.file.name}</span>
        <span className={`knowledge-batch-status knowledge-batch-status--${item.status}`}>
          {statusLabel(item)}
        </span>
      </div>
      <Input
        aria-label={`文档标题：${item.file.name}`}
        disabled={!canEdit}
        status={!item.title.trim() ? "error" : undefined}
        value={item.title}
        onChange={(event) => onChange({ title: event.target.value })}
      />
      {item.status === "uploading" ? (
        <Progress percent={Math.round(item.percent)} size="small" />
      ) : null}
      {item.error ? <span className="knowledge-batch-error">{item.error}</span> : null}
      {canEdit ? (
        <Button
          aria-label={`移除 ${item.file.name}`}
          className="knowledge-batch-remove"
          type="text"
          icon={<AppIcon name="Delete" size="sm" />}
          onClick={onRemove}
        />
      ) : null}
    </div>
  );
}

function statusLabel(item: BatchFileUploadItem) {
  if (item.status === "selected") return "待上传";
  if (item.status === "uploading") return `${Math.round(item.percent)}%`;
  if (item.status === "queued") return "已进入处理队列";
  return "上传失败";
}
