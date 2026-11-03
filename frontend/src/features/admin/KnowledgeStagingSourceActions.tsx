import { Button, Popconfirm, Space } from "antd";

import type { KnowledgeSourceActivity } from "@/shared/api/types";

type Props = {
  pendingSourceId: string | null;
  source: KnowledgeSourceActivity;
  onCleanup: (source: KnowledgeSourceActivity) => Promise<void>;
  onRetryConfirmation: (source: KnowledgeSourceActivity) => Promise<void>;
};

export function KnowledgeStagingSourceActions({
  pendingSourceId,
  source,
  onCleanup,
  onRetryConfirmation,
}: Props) {
  if (source.status !== "staging") return null;
  const pending = pendingSourceId === source.id;

  return (
    <Space size={4} wrap>
      <Button
        size="small"
        type="link"
        loading={pending}
        disabled={pending}
        onClick={() => void onRetryConfirmation(source)}
      >
        重试确认
      </Button>
      <Popconfirm
        cancelText="取消"
        description="会删除未确认的暂存文件，无法恢复。"
        okButtonProps={{ danger: true, loading: pending }}
        okText="清理"
        title="清理这次未完成上传？"
        onConfirm={() => {
          void onCleanup(source);
        }}
      >
        <Button danger size="small" type="link" disabled={pending}>
          清理
        </Button>
      </Popconfirm>
    </Space>
  );
}
