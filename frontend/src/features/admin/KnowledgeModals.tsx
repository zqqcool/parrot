import { Form, Input, Modal } from "antd";

import type { KnowledgeDocumentCreate } from "@/shared/api/types";
import { RequestErrorAlert } from "@/shared/ui";

type CreateModalProps<T> = {
  open: boolean;
  loading: boolean;
  error: Error | null;
  onCancel: () => void;
  onSubmit: (payload: T) => void;
};

export function CreateKnowledgeDocumentModal({
  open,
  loading,
  error,
  onCancel,
  onSubmit,
}: CreateModalProps<KnowledgeDocumentCreate>) {
  const [form] = Form.useForm<KnowledgeDocumentCreate>();

  return (
    <Modal
      title="新建知识文档"
      width={720}
      open={open}
      confirmLoading={loading}
      destroyOnHidden
      afterOpenChange={(visible) => !visible && form.resetFields()}
      onCancel={onCancel}
      onOk={() => void form.validateFields().then(onSubmit)}
    >
      <RequestErrorAlert error={error} fallback="创建知识文档失败" />
      <Form className="admin-modal-form" form={form} layout="vertical">
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
    </Modal>
  );
}
