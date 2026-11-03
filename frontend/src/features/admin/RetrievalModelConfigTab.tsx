import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Form, Popconfirm, Select } from "antd";
import type { DataTableProps } from "@/shared/ui";

import { RetrievalModelConfigModal } from "@/features/admin/RetrievalModelConfigModal";
import { providerDisplayName, providerOptions } from "@/features/admin/modelProviderCatalog";
import {
  createConfig,
  deleteEmbeddingConfig,
  listConfigs,
  testConfigConnection,
  updateConfig,
} from "@/features/admin/retrievalModelConfigApi";
import {
  configLabel,
  defaultValues,
  formValues,
  statusOptions,
  type ConfigKind,
  type RetrievalConfig,
  type RetrievalConfigForm as RetrievalConfigFormValues,
} from "@/features/admin/retrievalModelConfigTypes";
import type { EmbeddingConfig, ModelProvider } from "@/shared/api/types";
import {
  BinaryStatusTag,
  CreateButton,
  DataTable,
  RequestErrorAlert,
  SearchBar,
  useDebouncedValue,
} from "@/shared/ui";

type Props = {
  canManage: boolean;
  kind: ConfigKind;
  providers: ModelProvider[];
  tenantId: string;
};

export function RetrievalModelConfigTab({ canManage, kind, providers, tenantId }: Props) {
  const client = useQueryClient();
  const { message } = App.useApp();
  const [editing, setEditing] = useState<RetrievalConfig | null>(null);
  const [creating, setCreating] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "disabled">("all");
  const [form] = Form.useForm<RetrievalConfigFormValues>();
  const searchQuery = useDebouncedValue(searchValue.trim());
  const label = configLabel(kind);
  const query = useQuery({
    queryKey: ["admin", tenantId, `${kind}-configs`, searchQuery],
    queryFn: () => listConfigs(kind, tenantId, searchQuery),
  });
  const refresh = () =>
    client.invalidateQueries({ queryKey: ["admin", tenantId, `${kind}-configs`] });
  const closeModal = () => {
    setCreating(false);
    setEditing(null);
    form.resetFields();
  };
  const create = useMutation({
    mutationFn: (values: RetrievalConfigFormValues) => createConfig(kind, tenantId, values),
    onSuccess: async () => {
      closeModal();
      await refresh();
    },
  });
  const update = useMutation({
    mutationFn: (values: RetrievalConfigFormValues) =>
      updateConfig(kind, tenantId, editing?.id ?? "", values),
    onSuccess: async () => {
      closeModal();
      await refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (configId: string) => deleteEmbeddingConfig(tenantId, configId),
    onSuccess: refresh,
  });
  const testConnection = useMutation({
    mutationFn: (values: RetrievalConfigFormValues) =>
      testConfigConnection(kind, tenantId, values, editing?.id),
    onSuccess: () => void message.success("连接测试通过"),
    meta: { suppressGlobalErrorNotification: true },
  });
  const openCreate = () => {
    testConnection.reset();
    form.setFieldsValue(defaultValues(kind, providers));
    setCreating(true);
  };
  const openEdit = (config: RetrievalConfig) => {
    testConnection.reset();
    form.setFieldsValue(formValues(config));
    setEditing(config);
  };
  const save = () =>
    void form.validateFields().then((values) => (editing ? update : create).mutate(values));
  const test = () => void form.validateFields().then((values) => testConnection.mutate(values));
  const configs = (query.data ?? []).filter(
    (config) => statusFilter === "all" || config.status === statusFilter,
  );
  const mutation = editing ? update : create;

  const hasSelectableProvider = providerOptions(providers, kind).length > 0;
  return (
    <section aria-label={`${label} 配置`}>
      {!hasSelectableProvider ? (
        <Alert
          showIcon
          type="info"
          message={`当前接入的 OpenAI 与豆包暂不提供独立${label}能力，不能新建此类配置。存量配置仍可查看和测试。`}
        />
      ) : null}
      <SearchBar
        actions={canManage && hasSelectableProvider ? <CreateButton onClick={openCreate} /> : null}
        advancedFilters={
          <Select
            aria-label={`按状态筛选 ${label} 配置`}
            options={statusOptions}
            value={statusFilter}
            onChange={setStatusFilter}
          />
        }
        hasActiveFilters={statusFilter !== "all"}
        placeholder="搜索名称、模型或服务地址"
        value={searchValue}
        onChange={setSearchValue}
        onReset={() => {
          setSearchValue("");
          setStatusFilter("all");
        }}
      />
      <RequestErrorAlert error={query.error} fallback={`加载 ${label} 配置失败`} />
      <DataTable<RetrievalConfig>
        rowKey="id"
        loading={query.isFetching}
        dataSource={configs}
        resetPaginationKey={`${searchQuery}:${statusFilter}`}
        columns={columns(kind, canManage, providers, openEdit, (configId) =>
          remove.mutate(configId),
        )}
      />
      <RetrievalModelConfigModal
        editing={editing}
        form={form}
        kind={kind}
        open={creating || Boolean(editing)}
        providers={providers}
        saveError={mutation.error}
        saving={mutation.isPending}
        testing={testConnection.isPending}
        testError={testConnection.error}
        onCancel={closeModal}
        onSave={save}
        onTest={test}
      />
    </section>
  );
}

function columns(
  kind: ConfigKind,
  canManage: boolean,
  providers: ModelProvider[],
  onEdit: (config: RetrievalConfig) => void,
  onDelete: (configId: string) => void,
): NonNullable<DataTableProps<RetrievalConfig>["columns"]> {
  return [
    { title: "名称", dataIndex: "name" },
    {
      title: "供应商",
      dataIndex: "provider",
      render: (value: string) => providerDisplayName(providers, value),
    },
    { title: "模型", dataIndex: "model" },
    ...(kind === "embedding" ? [{ title: "向量维度", dataIndex: "embedding_dimension" }] : []),
    ...(kind === "embedding"
      ? [
          {
            title: "引用知识库",
            render: (_: unknown, config: RetrievalConfig) =>
              isEmbeddingConfig(config) ? config.reference_count : 0,
          },
        ]
      : []),
    {
      title: "凭据",
      dataIndex: "credential_configured",
      render: (value: boolean) => (
        <BinaryStatusTag active={value} activeLabel="已配置" inactiveLabel="未配置" />
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      render: (value: string) => (
        <BinaryStatusTag active={value === "active"} activeLabel="启用" inactiveLabel="停用" />
      ),
    },
    ...(canManage
      ? [
          {
            title: "操作",
            width: kind === "embedding" ? 140 : 80,
            render: (_: unknown, config: RetrievalConfig) => (
              <>
                <Button size="small" type="link" onClick={() => onEdit(config)}>
                  编辑
                </Button>
                {kind === "embedding" && isEmbeddingConfig(config) ? (
                  <Popconfirm
                    description="删除后不可恢复。"
                    disabled={!config.can_delete}
                    okText="删除"
                    okType="danger"
                    title="确认删除此 Embedding 配置？"
                    onConfirm={() => onDelete(config.id)}
                  >
                    <Button danger disabled={!config.can_delete} size="small" type="link">
                      删除
                    </Button>
                  </Popconfirm>
                ) : null}
              </>
            ),
          },
        ]
      : []),
  ];
}

function isEmbeddingConfig(config: RetrievalConfig): config is EmbeddingConfig {
  return "reference_count" in config;
}
