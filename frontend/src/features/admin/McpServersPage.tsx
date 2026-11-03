import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Form, Modal, Select, Space, Tag, Typography } from "antd";
import { Link } from "react-router-dom";

import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import {
  type McpServerFormValues,
  toMcpServerCreatePayload,
  toMcpServerUpdatePayload,
} from "@/features/admin/mcpServerForm";
import { McpServerFormFields } from "@/features/admin/McpServerFormFields";
import { McpServersPageActions } from "@/features/admin/McpServersPageActions";
import { McpToolRecallModal } from "@/features/admin/McpToolRecallModal";
import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import type { McpServer } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import {
  AdminPageHeader,
  BinaryStatusTag,
  DataTable,
  RequestErrorAlert,
  SearchBar,
  useDebouncedValue,
} from "@/shared/ui";

type McpServerForm = McpServerFormValues;

export function McpServersPage() {
  const tenantId = useTenantId();
  const auth = useAuth();
  const client = useQueryClient();
  const [editing, setEditing] = useState<McpServer | null>(null);
  const [creating, setCreating] = useState(false);
  const [recallOpen, setRecallOpen] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "disabled">("all");
  const [form] = Form.useForm<McpServerForm>();
  const canManage = auth.hasPermission("mcp_servers.manage");
  const canRecall = auth.hasPermission("agents.read");
  const query = useQuery({
    queryKey: ["admin", tenantId, "mcp-servers", searchQuery],
    queryFn: () => adminApi.listMcpServers(tenantId ?? "", searchQuery),
    enabled: Boolean(tenantId),
  });
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["admin", tenantId, "mcp-servers"] });
    await client.invalidateQueries({ queryKey: ["admin", tenantId, "dashboard"] });
  };
  const create = useMutation({
    mutationFn: (values: McpServerForm) =>
      adminApi.createMcpServer(tenantId ?? "", toMcpServerCreatePayload(values)),
    onSuccess: async () => {
      closeModal();
      await refresh();
    },
  });
  const update = useMutation({
    mutationFn: (values: McpServerForm) =>
      adminApi.updateMcpServer(tenantId ?? "", editing?.id ?? "", toMcpServerUpdatePayload(values)),
    onSuccess: async () => {
      closeModal();
      await refresh();
    },
  });
  const openCreate = () => {
    form.resetFields();
    form.setFieldsValue({ arguments: [], credentials: [], transport: "streamable_http" });
    setCreating(true);
  };
  const openEdit = (item: McpServer) => {
    form.setFieldsValue({
      name: item.name,
      transport: item.transport,
      endpoint: item.endpoint,
      arguments: item.arguments,
      status: item.status,
      credentials: item.credentials.map((credential) => ({ ...credential, secret: undefined })),
    });
    form.setFieldValue(
      "tool_policies",
      item.tool_policies.map((policy) => ({
        name: policy.name,
        description: policy.description,
        input_schema: policy.input_schema,
        effect: policy.effect,
        approval: policy.approval,
      })),
    );
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

  if (!tenantId) return <TenantRequiredState />;
  const open = creating || Boolean(editing);
  const mutation = editing ? update : create;
  const servers = (query.data ?? []).filter(
    (item) => statusFilter === "all" || item.status === statusFilter,
  );
  return (
    <section>
      <AdminPageHeader
        title="MCP 配置"
        description="管理当前租户的 MCP 服务端点和加密账户凭据；只有已绑定到 Agent 的启用服务会被运行时调用。"
      />
      <SearchBar
        actions={
          <McpServersPageActions
            canManage={canManage}
            canRecall={canRecall}
            onCreate={openCreate}
            onRecall={() => setRecallOpen(true)}
          />
        }
        advancedFilters={
          <Select
            aria-label="按状态筛选 MCP 配置"
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
        placeholder="搜索名称、协议或端点"
        value={searchValue}
        onChange={setSearchValue}
        onReset={() => {
          setSearchValue("");
          setStatusFilter("all");
        }}
      />
      <RequestErrorAlert error={query.error} fallback="加载 MCP 配置失败" />
      <DataTable<McpServer>
        rowKey="id"
        loading={query.isFetching}
        dataSource={servers}
        resetPaginationKey={`${searchQuery}:${statusFilter}`}
        scroll={{ x: 1120 }}
        columns={[
          { title: "名称", dataIndex: "name", width: 180 },
          { title: "传输协议", dataIndex: "transport", width: 150 },
          { title: "端点", dataIndex: "endpoint", ellipsis: true },
          {
            title: "关联 Agent",
            key: "bound_agents",
            width: 260,
            render: (_: unknown, item: McpServer) => <McpBoundAgents agents={item.bound_agents} />,
          },
          {
            title: "状态",
            dataIndex: "status",
            width: 100,
            render: (value: string) => (
              <BinaryStatusTag
                active={value === "active"}
                activeLabel="启用"
                inactiveLabel="停用"
              />
            ),
          },
          ...(canManage
            ? [
                {
                  title: "操作",
                  width: 90,
                  render: (_: unknown, item: McpServer) => (
                    <Button size="small" type="link" onClick={() => openEdit(item)}>
                      编辑
                    </Button>
                  ),
                },
              ]
            : []),
        ]}
      />
      <McpToolRecallModal
        canManageAgent={auth.hasPermission("agents.manage")}
        open={recallOpen}
        tenantId={tenantId}
        onClose={() => setRecallOpen(false)}
      />
      <Modal
        title={editing ? "编辑 MCP 配置" : "新增 MCP 配置"}
        width={840}
        open={open}
        confirmLoading={mutation.isPending}
        onCancel={closeModal}
        onOk={save}
      >
        <RequestErrorAlert error={mutation.error} fallback="保存 MCP 配置失败" />
        <Form className="admin-modal-form" form={form} layout="vertical">
          <McpServerFormFields
            editing={Boolean(editing)}
            form={form}
            server={editing}
            tenantId={tenantId}
          />
        </Form>
      </Modal>
    </section>
  );
}

function McpBoundAgents({ agents }: { agents: McpServer["bound_agents"] }) {
  if (agents === null) return <Typography.Text type="secondary">无查看权限</Typography.Text>;
  if (!agents?.length) return <Typography.Text type="secondary">暂无关联</Typography.Text>;
  return (
    <Space size={[4, 4]} wrap>
      {agents.map((agent) => (
        <Link
          aria-label={`查看关联 Agent ${agent.name}`}
          key={agent.id}
          to={`/admin/agents/${agent.id}`}
        >
          <Tag color="blue">{agent.name}</Tag>
        </Link>
      ))}
    </Space>
  );
}
