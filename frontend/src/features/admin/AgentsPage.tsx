import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Checkbox, Form, Input, message, Modal, Select } from "antd";
import { useNavigate } from "react-router-dom";

import { AgentCards } from "@/features/admin/AgentCards";
import { AgentTypeField } from "@/features/admin/AgentTypeField";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import type { AgentCreate } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import {
  AdminPageHeader,
  CreateButton,
  RequestErrorAlert,
  SearchBar,
  useDebouncedValue,
} from "@/shared/ui";

export function AgentsPage() {
  const tenantId = useTenantId();
  const client = useQueryClient();
  const auth = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const [publishedFilter, setPublishedFilter] = useState<"all" | "published" | "draft">("all");
  const [messageApi, messageContext] = message.useMessage();
  const [form] = Form.useForm<AgentCreate>();
  const query = useQuery({
    queryKey: ["admin", tenantId, "agents", searchQuery],
    queryFn: () => adminApi.listAgents(tenantId ?? "", searchQuery),
    enabled: Boolean(tenantId),
  });
  const agentTypes = useQuery({
    queryKey: ["admin", "agent-types"],
    queryFn: () => adminApi.listAgentTypes(),
    enabled: Boolean(tenantId),
  });
  const defaultAgentTypeKey = agentTypes.data?.find((agentType) => agentType.is_default)?.key;
  const agentTypeNames = new Map(
    agentTypes.data?.map((agentType) => [agentType.key, agentType.name]) ?? [],
  );

  useEffect(() => {
    if (open && defaultAgentTypeKey && !form.isFieldTouched("agent_type_key")) {
      form.setFieldValue("agent_type_key", defaultAgentTypeKey);
    }
  }, [defaultAgentTypeKey, form, open]);
  const create = useMutation({
    mutationFn: (values: AgentCreate) =>
      adminApi.createAgent(tenantId ?? "", {
        ...values,
        description: values.description ?? "",
        published: values.published ?? false,
        allow_anonymous: values.allow_anonymous ?? false,
      }),
    onSuccess: async () => {
      setOpen(false);
      form.resetFields();
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "agents"] });
      void messageApi.success("智能体已创建");
    },
  });
  if (!tenantId) return <TenantRequiredState />;
  const agents = (query.data ?? []).filter(
    (agent) =>
      publishedFilter === "all" ||
      (publishedFilter === "published" ? agent.published : !agent.published),
  );
  return (
    <section>
      {messageContext}
      <AdminPageHeader
        title="智能体管理"
        description="管理当前租户映射到统一运行时的智能体发布记录。"
      />
      <SearchBar
        actions={
          auth.hasPermission("agents.manage") ? (
            <CreateButton onClick={() => setOpen(true)} />
          ) : null
        }
        advancedFilters={
          <Select
            aria-label="按发布状态筛选智能体"
            options={[
              { value: "all", label: "全部状态" },
              { value: "published", label: "已发布" },
              { value: "draft", label: "草稿" },
            ]}
            value={publishedFilter}
            onChange={setPublishedFilter}
          />
        }
        hasActiveFilters={publishedFilter !== "all"}
        placeholder="搜索名称、标识或说明"
        value={searchValue}
        onChange={setSearchValue}
        onReset={() => {
          setSearchValue("");
          setPublishedFilter("all");
        }}
      />
      <RequestErrorAlert error={query.error} fallback="加载智能体失败，请稍后重试。" />
      <AgentCards
        agents={agents}
        agentTypeNames={agentTypeNames}
        loading={query.isFetching}
        tenantId={tenantId}
        onView={(agent) => void navigate(`/admin/agents/${agent.id}`)}
      />
      <Modal
        title="新建智能体发布"
        width={760}
        open={open}
        confirmLoading={create.isPending}
        onCancel={() => setOpen(false)}
        onOk={() => void form.validateFields().then((values) => create.mutate(values))}
      >
        <RequestErrorAlert error={create.error} fallback="创建智能体发布失败，请稍后重试。" />
        <RequestErrorAlert error={agentTypes.error} fallback="加载智能体类型失败，请稍后重试。" />
        <Form
          className="admin-modal-form"
          form={form}
          layout="vertical"
          initialValues={{ description: "", allow_anonymous: false }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: "请输入智能体名称" }]}
          >
            <Input placeholder="例如：客户支持助手" />
          </Form.Item>
          <Form.Item
            name="slug"
            label="公开标识"
            rules={[{ required: true, message: "请输入公开标识" }]}
          >
            <Input placeholder="例如：customer-support" />
          </Form.Item>
          <Form.Item
            className="admin-form-item-wide"
            name="runtime_agent_id"
            label="运行时智能体 ID"
            rules={[{ required: true, message: "请输入运行时智能体 ID" }]}
          >
            <Input placeholder="输入运行时智能体 ID" />
          </Form.Item>
          <Form.Item className="admin-form-item-wide" name="description" label="说明">
            <Input.TextArea rows={3} placeholder="简要说明智能体的能力和适用场景" />
          </Form.Item>
          <AgentTypeField
            agentTypes={agentTypes.data}
            disabled={agentTypes.isPending || !agentTypes.data}
          />
          <Form.Item
            className="admin-form-item-wide"
            name="allow_anonymous"
            valuePropName="checked"
          >
            <Checkbox>允许匿名访问</Checkbox>
          </Form.Item>
          <Alert
            className="admin-form-item-wide"
            type="info"
            showIcon
            message="创建后请配置默认 LLM，再从运行配置中发布。"
          />
        </Form>
      </Modal>
    </section>
  );
}
