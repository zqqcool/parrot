import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Form, Input, Modal } from "antd";

import { AgentTypeField } from "@/features/admin/AgentTypeField";
import { adminApi } from "@/shared/api/client";
import { endpoints } from "@/shared/api/endpoints";
import type { AdminAgent as Agent, AgentUpdate } from "@/shared/api/types";
import { RequestErrorAlert, UserAvatarUpload } from "@/shared/ui";
import { uploadObject } from "@/shared/uploads";

type Props = {
  agent: Agent;
  tenantId: string;
  open: boolean;
  onClose: () => void;
  onSuccessMessage: (content: string) => void;
};

type BasicValues = Pick<AgentUpdate, "agent_type_key" | "description" | "name">;

export function AgentBasicEditor({ agent, tenantId, open, onClose, onSuccessMessage }: Props) {
  const client = useQueryClient();
  const [form] = Form.useForm<BasicValues>();
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const update = useMutation({
    mutationFn: (values: BasicValues) => adminApi.updateAgent(tenantId, agent.id, values),
  });
  const attachAvatar = useMutation({
    mutationFn: async (file: File) => {
      const grant = await uploadObject({
        file,
        requestGrant: (metadata) =>
          adminApi.issueAgentAvatarUploadGrant(tenantId, agent.id, metadata),
      });
      return adminApi.attachAgentAvatar(tenantId, agent.id, { object_key: grant.object_key });
    },
  });
  const agentTypes = useQuery({
    queryKey: ["admin", "agent-types"],
    queryFn: () => adminApi.listAgentTypes(),
    enabled: open,
  });

  const save = async (values: BasicValues) => {
    let updated = await update.mutateAsync(values);
    if (avatarFile) updated = await attachAvatar.mutateAsync(avatarFile);
    client.setQueryData<Agent[]>(["admin", tenantId, "agents"], (items) =>
      items?.map((item) => (item.id === updated.id ? updated : item)),
    );
    onSuccessMessage(avatarFile ? "智能体信息和头像已保存" : "智能体基本信息已保存");
    setAvatarFile(null);
    onClose();
  };

  const saving = update.isPending || attachAvatar.isPending;
  const avatarUrl = agent.avatar_present
    ? endpoints.admin.agentAvatar(tenantId, agent.id)
    : undefined;

  return (
    <Modal
      title="编辑基本资料"
      width={720}
      style={{ top: 48 }}
      open={open}
      confirmLoading={saving}
      destroyOnHidden
      okText="保存"
      cancelText="取消"
      onCancel={() => {
        setAvatarFile(null);
        onClose();
      }}
      onOk={() => form.submit()}
    >
      <RequestErrorAlert error={update.error ?? attachAvatar.error} fallback="保存智能体信息失败" />
      <RequestErrorAlert error={agentTypes.error} fallback="加载智能体类型失败，请稍后重试。" />
      <Form<BasicValues>
        className="admin-modal-form"
        form={form}
        initialValues={{
          agent_type_key: agent.agent_type_key,
          description: agent.description,
          name: agent.name,
        }}
        layout="vertical"
        onFinish={(values) => void save(values)}
      >
        <Form.Item
          className="admin-form-item-wide"
          label="头像"
          extra="支持 PNG、JPEG、WebP，最大 2 MB。选择后随本次保存上传。"
        >
          <UserAvatarUpload
            avatarUrl={avatarUrl}
            disabled={saving}
            file={avatarFile}
            onChange={setAvatarFile}
          />
        </Form.Item>
        <Form.Item name="name" label="名称" rules={[{ required: true, message: "请输入名称" }]}>
          <Input maxLength={120} placeholder="输入智能体名称" />
        </Form.Item>
        <AgentTypeField
          agentTypes={agentTypes.data}
          disabled={agentTypes.isPending || !agentTypes.data}
        />
        <Form.Item className="admin-form-item-wide" name="description" label="说明">
          <Input.TextArea
            rows={4}
            maxLength={1000}
            showCount
            placeholder="简要说明智能体的能力和适用场景"
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
