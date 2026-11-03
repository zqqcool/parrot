import { Form, Radio } from "antd";

import type { AgentType } from "@/shared/api/types";

import "./agent-type-field.css";

type Props = {
  agentTypes: AgentType[] | undefined;
  disabled?: boolean;
};

export function AgentTypeField({ agentTypes, disabled = false }: Props) {
  return (
    <Form.Item
      className="agent-type-field admin-form-item-wide"
      name="agent_type_key"
      label="智能体类型"
      rules={[{ required: true, message: "请选择智能体类型" }]}
    >
      <Radio.Group className="agent-type-options" disabled={disabled}>
        {agentTypes?.map((agentType) => (
          <Radio className="agent-type-option" key={agentType.key} value={agentType.key}>
            <span className="agent-type-option-content">
              <span className="agent-type-option-heading">
                <strong>{agentType.name}</strong>
                {agentType.is_default ? (
                  <span className="agent-type-option-default">默认</span>
                ) : null}
              </span>
              <span className="agent-type-option-description">{agentType.description}</span>
            </span>
          </Radio>
        ))}
      </Radio.Group>
    </Form.Item>
  );
}
