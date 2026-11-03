import { Button, Form, Modal, Select, Typography } from "antd";
import { useMutation } from "@tanstack/react-query";

import { WebsocketChannelFormFields } from "@/features/admin/WebsocketChannelFormFields";
import { adminApi } from "@/shared/api/client";
import type { ImChannelCreate, ImChannelType } from "@/shared/api/types";
import { RequestErrorAlert } from "@/shared/ui";

type Props = {
  agentId: string;
  channelTypes: ImChannelType[];
  channelTypesLoading: boolean;
  open: boolean;
  tenantId: string;
  onClose: () => void;
  onCreated: () => Promise<void>;
};

export function ImChannelCreateModal({
  agentId,
  channelTypes,
  channelTypesLoading,
  open,
  tenantId,
  onClose,
  onCreated,
}: Props) {
  const [form] = Form.useForm<ImChannelCreate>();
  const selectedChannelType = Form.useWatch("channel_type", form) ?? "websocket";
  const selectedTypeEnabled = channelTypes.some(
    (item) => item.key === selectedChannelType && item.enabled,
  );
  const create = useMutation({
    mutationFn: async (payload: ImChannelCreate) => {
      const channel = await adminApi.createImChannel(tenantId, payload);
      return adminApi.bindImChannel(tenantId, channel.id, agentId);
    },
    onSuccess: async () => {
      form.resetFields();
      onClose();
      await onCreated();
    },
  });
  const close = () => {
    form.resetFields();
    onClose();
  };

  return (
    <Modal destroyOnHidden footer={null} open={open} title="创建渠道" width={760} onCancel={close}>
      <Typography.Paragraph type="secondary">
        {selectedChannelType === "websocket"
          ? "Origin 必须精确匹配，不支持通配符 *。创建后会自动绑定到当前 Agent。"
          : "选择已启用的渠道类型后，填写该渠道专属配置。"}
      </Typography.Paragraph>
      <Form
        className="agent-websocket-create-form"
        form={form}
        initialValues={{ channel_type: "websocket" }}
        layout="vertical"
        onFinish={(values) =>
          create.mutate({
            channel_type: values.channel_type,
            name: values.name.trim(),
            allowed_origins: (values.allowed_origins ?? [])
              .map((item) => item.trim())
              .filter(Boolean),
          })
        }
      >
        <Form.Item label="渠道类型" name="channel_type" rules={[{ required: true }]}>
          <Select
            loading={channelTypesLoading}
            options={channelTypes.map((item) => ({
              value: item.key,
              label: item.enabled ? item.label : `${item.label}（未接入）`,
              disabled: !item.enabled,
              title: item.description,
            }))}
          />
        </Form.Item>
        {selectedChannelType === "websocket" ? (
          <WebsocketChannelFormFields form={form} />
        ) : (
          <Typography.Text type="secondary">该渠道适配器尚未启用，无法填写配置。</Typography.Text>
        )}
        <div className="agent-websocket-create-actions">
          <Button
            disabled={!selectedTypeEnabled}
            htmlType="submit"
            loading={create.isPending}
            type="primary"
          >
            创建并绑定
          </Button>
        </div>
        <RequestErrorAlert error={create.error} fallback="创建渠道失败" />
      </Form>
    </Modal>
  );
}
