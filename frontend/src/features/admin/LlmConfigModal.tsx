import type { FormInstance } from "antd";
import { Form, Modal } from "antd";

import { LlmConfigFormFields } from "@/features/admin/LlmConfigFormFields";
import { ModelConnectionTestError } from "@/features/admin/ModelConnectionTestError";
import { ModelConfigModalFooter } from "@/features/admin/ModelConfigModalFooter";
import { providerCapability, providerDefaultValues } from "@/features/admin/modelProviderCatalog";
import type { LlmConfigForm } from "@/features/admin/llmConfigForm";
import type { LlmConfig, ModelProvider } from "@/shared/api/types";
import { RequestErrorAlert } from "@/shared/ui";

type Props = {
  editing: LlmConfig | null;
  form: FormInstance<LlmConfigForm>;
  onCancel: () => void;
  onSave: () => void;
  onTest: () => void;
  open: boolean;
  providers: ModelProvider[];
  saveError: unknown;
  saving: boolean;
  testing: boolean;
  testError: unknown;
};

export function LlmConfigModal({
  editing,
  form,
  onCancel,
  onSave,
  onTest,
  open,
  providers,
  saveError,
  saving,
  testing,
  testError,
}: Props) {
  const provider = Form.useWatch("provider", form);
  const applyProviderDefaults = (providerKey: string) => {
    const capability = providerCapability(providers, providerKey, "llm");
    form.setFieldsValue({
      model: capability?.default_model ?? "",
      base_url: capability?.default_base_url ?? "",
      ...providerDefaultValues(capability),
    });
  };
  return (
    <Modal
      cancelText="取消"
      confirmLoading={saving}
      footer={(_, { CancelBtn, OkBtn }) => (
        <ModelConfigModalFooter
          cancelButton={<CancelBtn />}
          disabled={saving}
          okButton={<OkBtn />}
          onTest={onTest}
          testing={testing}
        />
      )}
      okButtonProps={{ disabled: testing }}
      okText="确定"
      open={open}
      title={editing ? "编辑模型配置" : "新建模型配置"}
      width={640}
      onCancel={onCancel}
      onOk={onSave}
    >
      <RequestErrorAlert error={saveError} fallback="保存模型配置失败" />
      <ModelConnectionTestError error={testError} />
      <Form
        className="admin-modal-form"
        form={form}
        layout="vertical"
        onValuesChange={(changed: Partial<LlmConfigForm>) => {
          if (typeof changed.provider === "string") applyProviderDefaults(changed.provider);
        }}
      >
        <LlmConfigFormFields
          editing={Boolean(editing)}
          existingProvider={editing?.provider}
          provider={provider}
          providers={providers}
        />
      </Form>
    </Modal>
  );
}
