import { Checkbox, Form, Input, InputNumber, Select, Switch } from "antd";

import { providerCapability, providerOptions } from "@/features/admin/modelProviderCatalog";
import type { ModelProvider } from "@/shared/api/types";

type Props = {
  editing: boolean;
  existingProvider?: string;
  provider?: string;
  providers: ModelProvider[];
};

export function LlmConfigFormFields({ editing, existingProvider, provider, providers }: Props) {
  const capability = providerCapability(providers, provider, "llm");
  return (
    <>
      <Form.Item name="name" label="名称" rules={[{ required: true }]}>
        <Input placeholder="例如：生产环境 GPT-4.1" />
      </Form.Item>
      <Form.Item
        name="provider"
        label="供应商"
        extra={capability?.description}
        rules={[{ required: true }]}
      >
        <Select options={providerOptions(providers, "llm", provider)} placeholder="选择供应商" />
      </Form.Item>
      <Form.Item name="model" label="模型" rules={[{ required: true }]}>
        <Input placeholder={capability?.model_placeholder ?? "输入模型或推理接入点 ID"} />
      </Form.Item>
      <Form.Item
        name="base_url"
        label="服务地址"
        rules={[
          { required: true, message: "请输入服务地址" },
          { type: "url", message: "请输入有效的服务地址" },
        ]}
      >
        <Input placeholder={capability?.base_url_placeholder ?? "输入供应商服务地址"} />
      </Form.Item>
      <CredentialField editing={editing} existingProvider={existingProvider} provider={provider} />
      <Form.Item
        name="temperature"
        label="温度"
        rules={[{ required: true, message: "请输入温度" }]}
      >
        <InputNumber min={0} max={2} step={0.1} style={{ width: "100%" }} />
      </Form.Item>
      <Form.Item
        name="max_tokens"
        label="Max Tokens"
        rules={[{ required: true, message: "请输入 Max Tokens" }]}
      >
        <InputNumber min={1} max={32768} step={1} style={{ width: "100%" }} />
      </Form.Item>
      <Form.Item
        className="admin-form-item-wide"
        name="thinking_enabled"
        label="思考模式"
        valuePropName="checked"
        extra="请与上游模型端点的实际配置保持一致。开启后 Runtime 会使用兼容的工具选择策略；思考内容不会展示给最终用户。"
      >
        <Switch aria-label="启用模型思考模式" checkedChildren="已开启" unCheckedChildren="未开启" />
      </Form.Item>
      <Form.Item
        className="admin-form-item-wide"
        name="prompt_cache_enabled"
        label="Prompt Cache"
        valuePropName="checked"
        extra="仅在上游端点明确支持 prompt_cache_key / stream usage 时开启。开启后 Runtime 会发送稳定 cache key，并在管理诊断中记录 usage 与 cached_tokens；不支持的端点请保持关闭。"
      >
        <Switch
          aria-label="启用 Prompt Cache"
          checkedChildren="已开启"
          unCheckedChildren="未开启"
        />
      </Form.Item>
      <Form.Item className="admin-form-item-wide" name="is_default" valuePropName="checked">
        <Checkbox>设为默认模型</Checkbox>
      </Form.Item>
      {editing ? (
        <Form.Item
          className="admin-form-item-wide"
          name="status"
          label="状态"
          rules={[{ required: true }]}
        >
          <Select
            placeholder="选择配置状态"
            options={[
              { value: "active", label: "启用" },
              { value: "disabled", label: "停用" },
            ]}
          />
        </Form.Item>
      ) : null}
    </>
  );
}

function CredentialField({
  editing,
  existingProvider,
  provider,
}: {
  editing: boolean;
  existingProvider?: string;
  provider?: string;
}) {
  const required = !editing || provider !== existingProvider;
  const extra = required
    ? "新建或切换供应商时必须填写；凭据将加密保存且不会回显。"
    : "凭据已加密保存在 Parrot 数据库中；留空将保留原值。";
  const placeholder = required ? "输入供应商 API Key" : "留空保留原 API Key";
  const rules = required ? [{ required: true, message: "请输入 API Key" }] : [];
  return (
    <Form.Item
      name="api_key"
      className="admin-form-item-wide"
      label="API Key"
      extra={extra}
      rules={rules}
    >
      <Input.Password autoComplete="new-password" placeholder={placeholder} />
    </Form.Item>
  );
}
