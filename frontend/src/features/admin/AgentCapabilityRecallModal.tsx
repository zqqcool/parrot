import type { KeyboardEvent, ReactNode } from "react";
import { Alert, Button, Form, Input, InputNumber, Modal, Select, Space } from "antd";

import {
  type CapabilityRecallSearch,
  useCapabilityRecallController,
} from "@/features/admin/useCapabilityRecallController";
import { RequestErrorAlert } from "@/shared/ui";

type Props<TResult> = {
  canManageAgent: boolean;
  infoMessage: string;
  open: boolean;
  queryPlaceholder: string;
  renderResult: (result: TResult) => ReactNode;
  search: CapabilityRecallSearch<TResult>;
  tenantId: string;
  title: string;
  onClose: () => void;
};

export function AgentCapabilityRecallModal<TResult>(props: Props<TResult>) {
  const controller = useCapabilityRecallController<TResult>(props);
  return (
    <Modal
      cancelText="关闭"
      confirmLoading={controller.recall.isPending}
      destroyOnHidden
      okButtonProps={{ disabled: !controller.canSubmit }}
      okText="开始召回"
      open={props.open}
      title={props.title}
      width={720}
      onCancel={controller.close}
      onOk={controller.submit}
    >
      <Space className="skill-recall-modal-body" direction="vertical" size="middle">
        <Alert message={props.infoMessage} showIcon type="info" />
        <RecallForm
          controller={controller}
          queryPlaceholder={props.queryPlaceholder}
          recallTitle={props.title}
        />
        <RequestErrorAlert error={controller.agents.error} fallback="加载 Agent 失败" />
        <RequestErrorAlert error={controller.recall.error} fallback={`执行 ${props.title} 失败`} />
        <RequestErrorAlert
          error={controller.saveThreshold.error}
          fallback="应用 Agent 召回阈值失败"
        />
        {controller.saveThreshold.isSuccess ? (
          <Alert message="已应用到 Agent 后续召回" showIcon type="success" />
        ) : null}
        {controller.recall.data ? props.renderResult(controller.recall.data) : null}
      </Space>
    </Modal>
  );
}

type RecallController<TResult> = ReturnType<typeof useCapabilityRecallController<TResult>>;

function RecallForm<TResult>({
  controller,
  queryPlaceholder,
  recallTitle,
}: {
  controller: RecallController<TResult>;
  queryPlaceholder: string;
  recallTitle: string;
}) {
  return (
    <Form layout="vertical">
      <AgentField controller={controller} recallTitle={recallTitle} />
      <ThresholdField controller={controller} />
      <QueryField
        controller={controller}
        queryPlaceholder={queryPlaceholder}
        recallTitle={recallTitle}
      />
    </Form>
  );
}

function AgentField<TResult>({
  controller,
  recallTitle,
}: {
  controller: RecallController<TResult>;
  recallTitle: string;
}) {
  return (
    <Form.Item label="Agent" required>
      <Select
        aria-label={`选择用于 ${recallTitle}的 Agent`}
        disabled={controller.recall.isPending}
        loading={controller.agents.isFetching}
        optionFilterProp="label"
        options={controller.agentOptions}
        placeholder="请选择 Agent"
        showSearch
        value={controller.agentId}
        onChange={controller.selectAgent}
      />
    </Form.Item>
  );
}

function ThresholdField<TResult>({ controller }: { controller: RecallController<TResult> }) {
  const disabled =
    !controller.agentId || controller.recall.isPending || controller.saveThreshold.isPending;
  return (
    <Form.Item
      extra="验证时立即使用；点击应用后，才会影响该 Agent 后续的 Skill 和工具召回。向量不可用时安全降级为关键词召回。"
      label="最低相关度"
      required
    >
      <Space wrap>
        <InputNumber
          aria-label="设置 Agent 能力召回最低相关度"
          disabled={disabled}
          max={1}
          min={0}
          precision={2}
          step={0.05}
          value={controller.threshold}
          onChange={controller.changeThreshold}
        />
        {controller.canManageAgent ? (
          <Button
            disabled={!controller.canSave}
            loading={controller.saveThreshold.isPending}
            onClick={() => controller.saveThreshold.mutate()}
          >
            应用到 Agent
          </Button>
        ) : null}
      </Space>
    </Form.Item>
  );
}

function QueryField<TResult>({
  controller,
  queryPlaceholder,
  recallTitle,
}: {
  controller: RecallController<TResult>;
  queryPlaceholder: string;
  recallTitle: string;
}) {
  const handleShortcut = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.metaKey || event.ctrlKey) {
      event.preventDefault();
      controller.submit();
    }
  };
  return (
    <Form.Item label="用户问题" required>
      <Input.TextArea
        aria-label={`输入用于 ${recallTitle}的用户问题`}
        disabled={controller.recall.isPending}
        maxLength={500}
        placeholder={queryPlaceholder}
        rows={4}
        value={controller.query}
        onChange={(event) => controller.changeQuery(event.target.value)}
        onPressEnter={handleShortcut}
      />
    </Form.Item>
  );
}
