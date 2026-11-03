import { Form, Input, Modal, Select } from "antd";

import type { Memory, MemoryCreate } from "@/shared/api/types";
import { RequestErrorAlert } from "@/shared/ui";

export function CreateMemoryModal({
  open,
  form,
  loading,
  error,
  onCancel,
  onSubmit,
}: {
  open: boolean;
  form: ReturnType<typeof Form.useForm<MemoryCreate>>[0];
  loading: boolean;
  error: Error | null;
  onCancel: () => void;
  onSubmit: (payload: MemoryCreate) => void;
}) {
  return (
    <Modal
      title="新建记忆"
      open={open}
      confirmLoading={loading}
      destroyOnHidden
      onCancel={onCancel}
      onOk={() => void form.validateFields().then(onSubmit)}
    >
      <RequestErrorAlert error={error} fallback="创建记忆失败" />
      <Form
        className="admin-modal-form"
        form={form}
        layout="vertical"
        initialValues={{
          scope_type: "tenant",
          memory_type: "long_term_fact",
          retention_policy: "user_managed",
        }}
      >
        <Form.Item name="scope_type" label="范围类型" rules={[{ required: true }]}>
          <Select
            placeholder="选择记忆范围类型"
            options={["tenant", "agent", "user", "conversation"].map((value) => ({
              value,
              label: value,
            }))}
          />
        </Form.Item>
        <Form.Item name="scope_id" label="范围 ID" rules={[{ required: true }]}>
          <Input placeholder="输入范围对象 ID" />
        </Form.Item>
        <Form.Item name="agent_id" label="Agent ID（可选）">
          <Input placeholder="输入关联的 Agent ID" />
        </Form.Item>
        <Form.Item name="key" label="Key" rules={[{ required: true }]}>
          <Input placeholder="例如：preferred_language" />
        </Form.Item>
        <Form.Item name="memory_type" label="记忆类型" rules={[{ required: true }]}>
          <Select
            placeholder="选择记忆类型"
            options={[
              "user_preference",
              "project_convention",
              "long_term_fact",
              "session_state",
              "conversation_summary",
            ].map((value) => ({ value, label: value }))}
          />
        </Form.Item>
        <Form.Item
          className="admin-form-item-wide"
          name="content"
          label="内容"
          rules={[{ required: true }]}
        >
          <Input.TextArea rows={6} placeholder="输入需要保存的记忆内容" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export function EditMemoryModal({
  memory,
  loading,
  error,
  onCancel,
  onSubmit,
}: {
  memory: Memory | null;
  loading: boolean;
  error: Error | null;
  onCancel: () => void;
  onSubmit: (content: string) => void;
}) {
  const [form] = Form.useForm<{ content: string }>();
  return (
    <Modal
      title={`编辑记忆 · v${memory?.version ?? ""}`}
      open={Boolean(memory)}
      confirmLoading={loading}
      destroyOnHidden
      onCancel={onCancel}
      afterOpenChange={(open) => open && form.setFieldsValue({ content: memory?.content ?? "" })}
      onOk={() => void form.validateFields().then((value) => onSubmit(value.content))}
    >
      <RequestErrorAlert error={error} fallback="更新记忆失败" />
      <Form className="admin-modal-form" form={form} layout="vertical">
        <Form.Item
          className="admin-form-item-wide"
          name="content"
          label="内容"
          rules={[{ required: true }]}
        >
          <Input.TextArea rows={9} placeholder="输入更新后的记忆内容" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
