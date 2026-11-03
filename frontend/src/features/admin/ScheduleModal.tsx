import { Form, Input, Modal, Select } from "antd";

import { RequestErrorAlert } from "@/shared/ui";

import type { ScheduleForm } from "./scheduleForm";

export function ScheduleModal({
  open,
  form,
  agents,
  loading,
  error,
  onCancel,
  onSubmit,
  agentDisabled = false,
  defaultTimezone,
  title = "新建定时任务",
  errorFallback = "创建定时任务失败",
}: {
  open: boolean;
  form: ReturnType<typeof Form.useForm<ScheduleForm>>[0];
  agents: Array<{ label: string; value: string }>;
  loading: boolean;
  error: Error | null;
  onCancel: () => void;
  onSubmit: (values: ScheduleForm) => void;
  agentDisabled?: boolean;
  defaultTimezone?: string;
  title?: string;
  errorFallback?: string;
}) {
  const scheduleType = Form.useWatch("schedule_type", form) ?? "recurring";
  return (
    <Modal
      title={title}
      open={open}
      confirmLoading={loading}
      destroyOnHidden
      onCancel={onCancel}
      onOk={() => void form.validateFields().then(onSubmit)}
    >
      <RequestErrorAlert error={error} fallback={errorFallback} />
      <Form
        className="admin-modal-form"
        form={form}
        layout="vertical"
        initialValues={{ schedule_type: "recurring", timezone: defaultTimezone }}
      >
        <Form.Item name="title" label="任务名称" rules={[{ required: true }]}>
          <Input placeholder="例如：工作日晨报" />
        </Form.Item>
        <Form.Item name="agent_id" label="Agent" rules={[{ required: true }]}>
          <Select disabled={agentDisabled} options={agents} placeholder="选择已发布 Agent" />
        </Form.Item>
        <Form.Item name="schedule_type" label="任务类型" rules={[{ required: true }]}>
          <Select
            placeholder="选择任务类型"
            options={[
              { label: "周期任务", value: "recurring" },
              { label: "单次任务", value: "once" },
            ]}
          />
        </Form.Item>
        {scheduleType === "recurring" ? (
          <Form.Item name="cron_expr" label="Cron（分 时 日 月 星期）" rules={[{ required: true }]}>
            <Input placeholder="例如：0 9 * * 1-5" />
          </Form.Item>
        ) : (
          <Form.Item name="run_at" label="执行时间" rules={[{ required: true }]}>
            <Input type="datetime-local" />
          </Form.Item>
        )}
        <Form.Item name="timezone" label="时区" rules={[{ required: true }]}>
          <Input placeholder="例如：Asia/Shanghai" />
        </Form.Item>
        <Form.Item
          className="admin-form-item-wide"
          name="input_text"
          label="执行指令"
          rules={[{ required: true }]}
        >
          <Input.TextArea rows={5} placeholder="输入定时执行时发送给 Agent 的完整指令" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
