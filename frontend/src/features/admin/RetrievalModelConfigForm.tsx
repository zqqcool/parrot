import { Alert, Form, Input, InputNumber, Select } from "antd";

import { providerCapability, providerOptions } from "./modelProviderCatalog";
import type { RetrievalConfig, RetrievalConfigForm } from "./retrievalModelConfigTypes";
import { configLabel, statusOptions, type ConfigKind } from "./retrievalModelConfigTypes";
import type { ModelProvider } from "@/shared/api/types";

type Props = {
  editing: RetrievalConfig | null;
  form: ReturnType<typeof Form.useForm<RetrievalConfigForm>>[0];
  kind: ConfigKind;
  onValuesChange?: (changed: Partial<RetrievalConfigForm>) => void;
  providers: ModelProvider[];
};

export function RetrievalModelConfigForm({
  editing,
  form,
  kind,
  onValuesChange,
  providers,
}: Props) {
  const label = configLabel(kind);
  const identityLocked = kind === "embedding" && editing !== null;
  const provider = Form.useWatch("provider", form);
  const capability = providerCapability(providers, provider, kind);
  return (
    <Form
      className="admin-modal-form"
      form={form}
      layout="vertical"
      onValuesChange={(changed: Partial<RetrievalConfigForm>) => onValuesChange?.(changed)}
    >
      <IdentityNotice visible={identityLocked} />
      <Form.Item name="name" label="名称" rules={[{ required: true }]}>
        <Input placeholder={`例如：${label} 生产配置`} />
      </Form.Item>
      <Form.Item
        name="provider"
        label="供应商"
        extra={capability?.description}
        rules={[{ required: true, message: "请选择供应商" }]}
      >
        <Select
          disabled={identityLocked}
          options={providerOptions(providers, kind, provider)}
          placeholder="选择供应商"
        />
      </Form.Item>
      <Form.Item name="model" label="模型" rules={[{ required: true }]}>
        <Input
          disabled={identityLocked}
          placeholder={capability?.model_placeholder ?? "输入模型或推理接入点 ID"}
        />
      </Form.Item>
      <Form.Item
        name="base_url"
        label="服务地址"
        rules={[
          { required: true, message: "请输入服务地址" },
          { type: "url", message: "请输入有效的服务地址" },
        ]}
      >
        <Input
          disabled={identityLocked}
          placeholder={capability?.base_url_placeholder ?? "输入供应商服务地址"}
        />
      </Form.Item>
      <CredentialFields
        credentialType={capability?.credential_type ?? "api_key"}
        editing={Boolean(editing)}
      />
      <EmbeddingDimensionField disabled={identityLocked} visible={kind === "embedding"} />
      <StatusField visible={Boolean(editing)} />
    </Form>
  );
}

function IdentityNotice({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <Alert
      showIcon
      type="info"
      message="Embedding 的供应商、地址、模型和向量维度不可修改；如需变更，请新建配置。"
    />
  );
}

function CredentialFields({
  credentialType,
  editing,
}: {
  credentialType: "api_key" | "access_key_pair";
  editing: boolean;
}) {
  if (credentialType === "access_key_pair") {
    return <AccessKeyPairFields editing={editing} />;
  }
  const extra = editing
    ? "凭据已加密保存；留空将保留原值。"
    : "凭据将加密保存，不会在页面或接口中回显。";
  const placeholder = editing ? "留空保留原 API Key" : "输入服务 API Key";
  const rules = editing ? [] : [{ required: true, message: "请输入 API Key" }];
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

function AccessKeyPairFields({ editing }: { editing: boolean }) {
  const extra = editing
    ? "AK/SK 已加密保存；两个字段均留空将保留原值。"
    : "使用供应商要求的访问密钥；AK/SK 均会加密保存且不会回显。";
  const requiredRules = editing ? [] : [{ required: true, message: "请输入供应商访问密钥" }];
  return (
    <>
      <Form.Item name="access_key_id" label="Access Key ID（AK）" rules={requiredRules}>
        <Input.Password
          autoComplete="new-password"
          placeholder={editing ? "留空保留原 AK" : "输入供应商 Access Key ID"}
        />
      </Form.Item>
      <Form.Item
        name="secret_access_key"
        dependencies={["access_key_id"]}
        className="admin-form-item-wide"
        label="Secret Access Key（SK）"
        extra={extra}
        rules={[
          ...requiredRules,
          ({ getFieldValue }) => ({
            validator: (_, value: string | undefined) => {
              const accessKeyId = getFieldValue("access_key_id") as string | undefined;
              if (Boolean(value) === Boolean(accessKeyId)) return Promise.resolve();
              return Promise.reject(new Error("AK 与 SK 必须同时填写，或同时留空以保留原值"));
            },
          }),
        ]}
      >
        <Input.Password
          autoComplete="new-password"
          placeholder={editing ? "留空保留原 SK" : "输入供应商 Secret Access Key"}
        />
      </Form.Item>
    </>
  );
}

function EmbeddingDimensionField({ disabled, visible }: { disabled: boolean; visible: boolean }) {
  if (!visible) return null;
  return (
    <Form.Item
      name="embedding_dimension"
      label="向量维度"
      extra="必须与服务实际返回的向量维度一致。配置被知识库引用后不可修改。"
      rules={[{ required: true, type: "number", min: 8, max: 16384 }]}
    >
      <InputNumber
        disabled={disabled}
        min={8}
        max={16384}
        precision={0}
        style={{ width: "100%" }}
      />
    </Form.Item>
  );
}

function StatusField({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <Form.Item name="status" label="状态" rules={[{ required: true }]}>
      <Select options={statusOptions.slice(1)} />
    </Form.Item>
  );
}
