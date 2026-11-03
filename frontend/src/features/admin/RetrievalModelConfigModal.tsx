import type { FormInstance } from "antd";
import { Modal } from "antd";

import { ModelConfigModalFooter } from "./ModelConfigModalFooter";
import { ModelConnectionTestError } from "./ModelConnectionTestError";
import { RetrievalModelConfigForm } from "./RetrievalModelConfigForm";
import { providerCapability, providerDefaultValues, providerOptions } from "./modelProviderCatalog";
import {
  configLabel,
  type ConfigKind,
  type RetrievalConfig,
  type RetrievalConfigForm as RetrievalConfigFormValues,
} from "./retrievalModelConfigTypes";
import type { ModelProvider } from "@/shared/api/types";
import { RequestErrorAlert } from "@/shared/ui";

type Props = {
  editing: RetrievalConfig | null;
  form: FormInstance<RetrievalConfigFormValues>;
  kind: ConfigKind;
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

export function RetrievalModelConfigModal({
  editing,
  form,
  kind,
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
  const hasSelectableProvider = providerOptions(providers, kind).length > 0;
  const applyProviderDefaults = (providerKey: string) => {
    const capability = providerCapability(providers, providerKey, kind);
    form.setFieldsValue({
      model: capability?.default_model ?? "",
      base_url: capability?.default_base_url ?? "",
      api_key: undefined,
      access_key_id: undefined,
      secret_access_key: undefined,
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
          disabled={saving || (!editing && !hasSelectableProvider)}
          okButton={<OkBtn />}
          onTest={onTest}
          testing={testing}
        />
      )}
      okButtonProps={{ disabled: testing || (!editing && !hasSelectableProvider) }}
      okText="确定"
      open={open}
      title={`${editing ? "编辑" : "新建"}${configLabel(kind)} 配置`}
      width={640}
      onCancel={onCancel}
      onOk={onSave}
    >
      <RequestErrorAlert error={saveError} fallback={`保存 ${configLabel(kind)} 配置失败`} />
      <ModelConnectionTestError error={testError} />
      <RetrievalModelConfigForm
        editing={editing}
        form={form}
        kind={kind}
        providers={providers}
        onValuesChange={(changed) => {
          if (typeof changed.provider === "string") applyProviderDefaults(changed.provider);
        }}
      />
    </Modal>
  );
}
