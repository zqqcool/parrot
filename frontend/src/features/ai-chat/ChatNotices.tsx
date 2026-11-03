import { Alert, Button, Space } from "antd";

import type { PendingActionReference } from "@/features/ai-chat/transport/InteractionSocket";

export type OutputState =
  "partial" | "waiting_user_input" | "waiting_user_action" | "failed" | null;

type ChatNoticesProps = {
  outputState: OutputState;
  pendingAction: PendingActionReference | null;
  resolvingAction: boolean;
  onResolveAction: (decision: "approve" | "reject") => void;
};

export function ChatNotices({
  outputState,
  pendingAction,
  resolvingAction,
  onResolveAction,
}: ChatNoticesProps) {
  if (!outputState) return null;
  return (
    <section className="chat-notices" aria-live="polite">
      <OutputStateNotice
        outputState={outputState}
        pendingAction={pendingAction}
        resolvingAction={resolvingAction}
        onResolveAction={onResolveAction}
      />
    </section>
  );
}

function OutputStateNotice({
  outputState,
  pendingAction,
  resolvingAction,
  onResolveAction,
}: ChatNoticesProps) {
  if (outputState === "partial") {
    return (
      <Alert
        type="warning"
        message="已返回部分结果"
        description="运行预算已到达边界，以下内容不是完整成功结果。"
        showIcon
      />
    );
  }
  if (outputState === "waiting_user_input") {
    return (
      <Alert
        type="info"
        message="等待补充信息"
        description="请在下方补充必要信息，当前对话会在同一安全通道中继续。"
        showIcon
      />
    );
  }
  if (outputState === "failed") {
    return (
      <Alert
        type="error"
        message="本次运行失败"
        description="未能获得模型结果，请稍后重试；如持续失败，请联系管理员。"
        showIcon
      />
    );
  }
  if (outputState === "waiting_user_action" && pendingAction) {
    return (
      <Alert
        type="warning"
        message="等待操作确认"
        description="请确认是否继续。系统只会执行当前已校验并持久化的操作。"
        action={
          <Space>
            <Button disabled={resolvingAction} onClick={() => onResolveAction("reject")}>
              拒绝
            </Button>
            <Button
              type="primary"
              loading={resolvingAction}
              onClick={() => onResolveAction("approve")}
            >
              批准
            </Button>
          </Space>
        }
        showIcon
      />
    );
  }
  return null;
}
