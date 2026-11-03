import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Checkbox, Form, Modal } from "antd";

import { adminApi } from "@/shared/api/client";
import type { AdminAgent as Agent, AgentUpdate } from "@/shared/api/types";
import { RequestErrorAlert } from "@/shared/ui";

type Props = {
  agent: Agent;
  tenantId: string;
  open: boolean;
  onClose: () => void;
  onSuccessMessage: (content: string) => void;
};

type AnonymousAccessValues = Pick<AgentUpdate, "allow_anonymous">;

export function AgentAnonymousAccessEditor({
  agent,
  tenantId,
  open,
  onClose,
  onSuccessMessage,
}: Props) {
  const client = useQueryClient();
  const [form] = Form.useForm<AnonymousAccessValues>();
  const update = useMutation({
    mutationFn: (values: AnonymousAccessValues) => adminApi.updateAgent(tenantId, agent.id, values),
  });

  const save = async (values: AnonymousAccessValues) => {
    const updated = await update.mutateAsync(values);
    client.setQueryData<Agent[]>(["admin", tenantId, "agents"], (items) =>
      items?.map((item) => (item.id === updated.id ? updated : item)),
    );
    onSuccessMessage("匿名访问范围已更新");
    onClose();
  };

  return (
    <Modal
      cancelText="取消"
      confirmLoading={update.isPending}
      destroyOnHidden
      okText="确认保存"
      open={open}
      title="调整匿名访问"
      width={480}
      onCancel={onClose}
      onOk={() => form.submit()}
    >
      <RequestErrorAlert error={update.error} fallback="更新匿名访问范围失败" />
      <Form<AnonymousAccessValues>
        form={form}
        initialValues={{ allow_anonymous: agent.allow_anonymous }}
        layout="vertical"
        onFinish={(values) => void save(values)}
      >
        <Form.Item
          extra="开启后，未登录访客可访问已发布且已启用的智能体；发布与运行状态仍需单独控制。"
          name="allow_anonymous"
          valuePropName="checked"
        >
          <Checkbox>允许匿名访问</Checkbox>
        </Form.Item>
      </Form>
    </Modal>
  );
}
