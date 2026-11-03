import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Form, Input, Modal, Segmented } from "antd";

import { adminApi } from "@/shared/api/client";
import type { AdminAgent as Agent, AgentUpdate } from "@/shared/api/types";
import { MarkdownPreview, RequestErrorAlert } from "@/shared/ui";

type Props = {
  agent: Agent;
  tenantId: string;
  open: boolean;
  onClose: () => void;
  onSuccessMessage: (content: string) => void;
};

type SystemPromptValues = Pick<AgentUpdate, "system_prompt">;
type SystemPromptMode = "edit" | "preview";

export function AgentSystemPromptEditor({
  agent,
  tenantId,
  open,
  onClose,
  onSuccessMessage,
}: Props) {
  const client = useQueryClient();
  const [form] = Form.useForm<SystemPromptValues>();
  const [mode, setMode] = useState<SystemPromptMode>("edit");
  const update = useMutation({
    mutationFn: (values: SystemPromptValues) => adminApi.updateAgent(tenantId, agent.id, values),
  });
  const promptLabel = (
    <span className="agent-system-prompt-label">
      系统提示词
      <Segmented<SystemPromptMode>
        aria-label="系统提示词显示模式"
        options={[
          { label: "编辑", value: "edit" },
          { label: "预览", value: "preview" },
        ]}
        size="small"
        value={mode}
        onChange={setMode}
      />
    </span>
  );
  const promptExtra =
    "运行时会将此内容作为 Agent 专属系统指令；不要填写访问令牌、密码或其他敏感凭据。";

  const close = () => {
    setMode("edit");
    onClose();
  };
  const save = async (values: SystemPromptValues) => {
    const updated = await update.mutateAsync(values);
    client.setQueryData<Agent[]>(["admin", tenantId, "agents"], (items) =>
      items?.map((item) => (item.id === updated.id ? updated : item)),
    );
    onSuccessMessage("系统提示词已保存");
    close();
  };

  return (
    <Modal
      cancelText="取消"
      confirmLoading={update.isPending}
      destroyOnHidden
      okText="保存"
      open={open}
      style={{ top: 48 }}
      title="编辑系统提示词"
      width={820}
      onCancel={close}
      onOk={() => form.submit()}
    >
      <RequestErrorAlert error={update.error} fallback="保存系统提示词失败" />
      <Form<SystemPromptValues>
        form={form}
        initialValues={{ system_prompt: agent.system_prompt }}
        layout="vertical"
        onFinish={(values) => void save(values)}
      >
        {mode === "edit" ? (
          <Form.Item extra={promptExtra} label={promptLabel} name="system_prompt">
            <Input.TextArea
              aria-label="系统提示词"
              maxLength={20_000}
              placeholder="定义角色、行为边界、输出风格和任务规则"
              rows={12}
              showCount
            />
          </Form.Item>
        ) : (
          <Form.Item extra={promptExtra} label={promptLabel}>
            <Form.Item noStyle shouldUpdate>
              {({ getFieldValue }) => {
                const value: unknown = getFieldValue("system_prompt");
                return (
                  <div className="agent-system-prompt-preview">
                    <MarkdownPreview
                      value={typeof value === "string" && value ? value : "_暂无系统提示词_"}
                    />
                  </div>
                );
              }}
            </Form.Item>
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
}
