import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Form, Select, Tabs } from "antd";

import { LlmConfigModal } from "@/features/admin/LlmConfigModal";
import { RetrievalModelConfigTab } from "@/features/admin/RetrievalModelConfigTab";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import {
  createLlmConfigPayload,
  llmConnectionTestPayload,
  type LlmConfigForm,
  updateLlmConfigPayload,
} from "@/features/admin/llmConfigForm";
import {
  providerCapability,
  providerDefaultValues,
  providerDisplayName,
  providerOptions,
} from "@/features/admin/modelProviderCatalog";
import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import type { LlmConfig, ModelProvider } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import {
  AdminPageHeader,
  BinaryStatusTag,
  CreateButton,
  DataTable,
  RequestErrorAlert,
  SearchBar,
  useDebouncedValue,
} from "@/shared/ui";

import "./model-config.css";

type LlmConfigsTabProps = {
  canManage: boolean;
  providers: ModelProvider[];
  tenantId: string;
};

function LlmConfigsTab({ canManage, providers, tenantId }: LlmConfigsTabProps) {
  const client = useQueryClient();
  const { message } = App.useApp();
  const [editing, setEditing] = useState<LlmConfig | null>(null);
  const [creating, setCreating] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "disabled">("all");
  const [form] = Form.useForm<LlmConfigForm>();
  const query = useQuery({
    queryKey: ["admin", tenantId, "llm-configs", searchQuery],
    queryFn: () => adminApi.listLlmConfigs(tenantId, searchQuery),
  });
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["admin", tenantId, "llm-configs"] });
    await client.invalidateQueries({ queryKey: ["admin", tenantId, "dashboard"] });
  };
  const create = useMutation({
    mutationFn: (values: LlmConfigForm) =>
      adminApi.createLlmConfig(tenantId, createLlmConfigPayload(values)),
    onSuccess: async () => {
      closeModal();
      await refresh();
    },
  });
  const update = useMutation({
    mutationFn: (values: LlmConfigForm) =>
      adminApi.updateLlmConfig(tenantId, editing?.id ?? "", updateLlmConfigPayload(values)),
    onSuccess: async () => {
      closeModal();
      await refresh();
    },
  });
  const testConnection = useMutation({
    mutationFn: (values: LlmConfigForm) =>
      adminApi.testLlmConfigDraftConnection(
        tenantId,
        llmConnectionTestPayload(values, editing?.id),
      ),
    onSuccess: () => void message.success("连接测试通过"),
    meta: { suppressGlobalErrorNotification: true },
  });
  const openCreate = () => {
    testConnection.reset();
    form.resetFields();
    const provider = providerOptions(providers, "llm")[0]?.value;
    form.setFieldsValue({
      provider,
      ...providerDefaultValues(providerCapability(providers, provider, "llm")),
      is_default: false,
      temperature: 0.2,
      max_tokens: 4096,
      thinking_enabled: false,
      prompt_cache_enabled: false,
    });
    setCreating(true);
  };
  const openEdit = (item: LlmConfig) => {
    testConnection.reset();
    form.setFieldsValue({ ...item, api_key: undefined, base_url: item.base_url ?? undefined });
    setEditing(item);
  };
  const closeModal = () => {
    setCreating(false);
    setEditing(null);
    form.resetFields();
  };
  const save = () =>
    void form.validateFields().then((values) => {
      if (editing) update.mutate(values);
      else create.mutate(values);
    });
  const test = () => void form.validateFields().then((values) => testConnection.mutate(values));

  const open = creating || Boolean(editing);
  const mutation = editing ? update : create;
  const configs = (query.data ?? []).filter(
    (item) => statusFilter === "all" || item.status === statusFilter,
  );
  const canCreate = providerOptions(providers, "llm").length > 0;
  return (
    <section>
      <SearchBar
        actions={canManage && canCreate ? <CreateButton onClick={openCreate} /> : null}
        advancedFilters={
          <Select
            aria-label="按状态筛选模型配置"
            options={[
              { value: "all", label: "全部状态" },
              { value: "active", label: "启用" },
              { value: "disabled", label: "停用" },
            ]}
            value={statusFilter}
            onChange={setStatusFilter}
          />
        }
        hasActiveFilters={statusFilter !== "all"}
        placeholder="搜索名称、供应商或模型"
        value={searchValue}
        onChange={setSearchValue}
        onReset={() => {
          setSearchValue("");
          setStatusFilter("all");
        }}
      />
      <RequestErrorAlert error={query.error} fallback="加载模型配置失败" />
      <DataTable<LlmConfig>
        rowKey="id"
        loading={query.isFetching}
        dataSource={configs}
        resetPaginationKey={`${searchQuery}:${statusFilter}`}
        columns={[
          { title: "名称", dataIndex: "name" },
          {
            title: "供应商",
            dataIndex: "provider",
            render: (value: string) => providerDisplayName(providers, value),
          },
          { title: "模型", dataIndex: "model" },
          {
            title: "凭据",
            dataIndex: "credential_configured",
            render: (value: boolean) => (
              <BinaryStatusTag active={value} activeLabel="已配置" inactiveLabel="未配置" />
            ),
          },
          { title: "温度", dataIndex: "temperature" },
          { title: "Max Tokens", dataIndex: "max_tokens" },
          {
            title: "思考模式",
            dataIndex: "thinking_enabled",
            render: (value: boolean) => (
              <BinaryStatusTag active={value} activeLabel="已开启" inactiveLabel="未开启" />
            ),
          },
          {
            title: "Prompt Cache",
            dataIndex: "prompt_cache_enabled",
            render: (value: boolean) => (
              <BinaryStatusTag active={value} activeLabel="已开启" inactiveLabel="未开启" />
            ),
          },
          {
            title: "状态",
            dataIndex: "status",
            render: (value: string) => (
              <BinaryStatusTag
                active={value === "active"}
                activeLabel="启用"
                inactiveLabel="停用"
              />
            ),
          },
          {
            title: "默认",
            dataIndex: "is_default",
            render: (value: boolean) => (value ? "是" : "否"),
          },
          ...(canManage
            ? [
                {
                  title: "操作",
                  width: 80,
                  render: (_: unknown, item: LlmConfig) => (
                    <Button size="small" type="link" onClick={() => openEdit(item)}>
                      编辑
                    </Button>
                  ),
                },
              ]
            : []),
        ]}
      />
      <LlmConfigModal
        editing={editing}
        form={form}
        open={open}
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

export function LlmConfigsPage() {
  const tenantId = useTenantId();
  const auth = useAuth();
  const providers = useQuery({
    enabled: Boolean(tenantId),
    queryKey: ["admin", tenantId, "model-providers"],
    queryFn: () => adminApi.listModelProviders(tenantId ?? ""),
  });
  if (!tenantId) return <TenantRequiredState />;
  const canManage = auth.hasPermission("llm_configs.manage");
  return (
    <section>
      <AdminPageHeader
        title="模型配置"
        description="统一管理当前租户的 LLM、Embedding 与重排序模型。凭据均会加密保存；知识库仅在明确授权后使用外部检索模型。"
      />
      <RequestErrorAlert error={providers.error} fallback="加载模型供应商失败" />
      <Tabs
        className="model-config-tabs"
        defaultActiveKey="llm"
        size="small"
        items={[
          {
            key: "llm",
            label: "LLM",
            children: (
              <LlmConfigsTab
                canManage={canManage}
                providers={providers.data ?? []}
                tenantId={tenantId}
              />
            ),
          },
          {
            key: "embedding",
            label: "Embedding",
            children: (
              <RetrievalModelConfigTab
                canManage={canManage}
                kind="embedding"
                providers={providers.data ?? []}
                tenantId={tenantId}
              />
            ),
          },
          {
            key: "reranker",
            label: "重排序",
            children: (
              <RetrievalModelConfigTab
                canManage={canManage}
                kind="reranker"
                providers={providers.data ?? []}
                tenantId={tenantId}
              />
            ),
          },
        ]}
      />
    </section>
  );
}
