import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Popconfirm, Space } from "antd";
import { Link } from "react-router-dom";

import { adminApi } from "@/shared/api/client";
import type { AdminAgent as Agent, McpServer } from "@/shared/api/types";
import { BinaryStatusTag, DataTable, RequestErrorAlert } from "@/shared/ui";

type Props = {
  agent: Agent;
  canManage: boolean;
  canRead: boolean;
  tenantId: string;
  onSaved: () => void;
};

type BindingChange = {
  ids: string[];
  serverId: string;
};

export function AgentMcpSection({ agent, canManage, canRead, onSaved, tenantId }: Props) {
  const client = useQueryClient();
  const [ids, setIds] = useState<string[]>([]);
  const servers = useQuery({
    queryKey: ["admin", tenantId, "mcp-servers"],
    queryFn: () => adminApi.listMcpServers(tenantId),
    enabled: canRead,
  });
  const bindings = useQuery({
    queryKey: ["admin", tenantId, "agents", agent.id, "mcp-servers"],
    queryFn: () => adminApi.getAgentMcpServerBindings(tenantId, agent.id),
    enabled: canRead,
  });
  const update = useMutation({
    mutationFn: ({ ids: nextIds }: BindingChange) =>
      adminApi.replaceAgentMcpServerBindings(tenantId, agent.id, { ids: nextIds }),
    onMutate: ({ ids: nextIds }) => {
      const previousIds = ids;
      setIds(nextIds);
      return { previousIds };
    },
    onError: (_, __, context) => {
      setIds(context?.previousIds ?? []);
    },
    onSuccess: (data) => {
      client.setQueryData(["admin", tenantId, "agents", agent.id, "mcp-servers"], data);
      setIds([...data.ids]);
      onSaved();
    },
  });

  useEffect(() => {
    if (bindings.data) setIds([...bindings.data.ids]);
  }, [bindings.data]);

  if (!canRead) {
    return <Alert showIcon type="info" message="当前账号没有查看 MCP 配置的权限。" />;
  }

  const availableServers = (servers.data ?? []).filter((item) => item.status === "active");
  return (
    <section className="agent-tab-panel">
      <div className="agent-tab-heading">
        <div>
          <h2>MCP 服务绑定</h2>
          <p>仅已绑定的启用租户 MCP 服务可被当前 Agent 在运行时调用。</p>
        </div>
        <Space wrap>
          <Link className="ant-btn" to="/admin/mcp-servers">
            管理 MCP 服务
          </Link>
        </Space>
      </div>
      <Alert
        showIcon
        type="info"
        message="系统 MCP 服务由平台管理员统一管理，所有 Agent 默认可用，无需在此重复绑定。"
      />
      <RequestErrorAlert error={servers.error ?? bindings.error} fallback="加载 MCP 配置失败" />
      <DataTable<McpServer>
        rowKey="id"
        loading={servers.isPending || bindings.isPending}
        dataSource={availableServers}
        scroll={{ x: 860 }}
        locale={{ emptyText: "当前租户暂无可绑定的启用 MCP 服务" }}
        columns={[
          {
            title: "当前 Agent",
            key: "binding",
            width: 128,
            render: (_, item) =>
              ids.includes(item.id) ? (
                <BinaryStatusTag active activeLabel="已绑定" inactiveLabel="" activeColor="blue" />
              ) : (
                "-"
              ),
          },
          { title: "名称", dataIndex: "name", width: 180, ellipsis: true },
          { title: "传输协议", dataIndex: "transport", width: 150, ellipsis: true },
          { title: "端点", dataIndex: "endpoint", ellipsis: true },
          {
            title: "状态",
            dataIndex: "status",
            width: 100,
            render: (status: string) => (
              <BinaryStatusTag
                active={status === "active"}
                activeLabel="启用"
                inactiveLabel="停用"
              />
            ),
          },
          {
            title: "操作",
            key: "action",
            width: 128,
            align: "right",
            render: (_, item) => {
              const bound = ids.includes(item.id);
              return (
                <McpBindingAction
                  bound={bound}
                  disabled={!canManage || update.isPending}
                  loading={update.isPending && update.variables?.serverId === item.id}
                  onChange={() =>
                    update.mutate({
                      serverId: item.id,
                      ids: bound ? ids.filter((id) => id !== item.id) : [...ids, item.id],
                    })
                  }
                />
              );
            },
          },
        ]}
      />
      <RequestErrorAlert error={update.error} fallback="更新 MCP 关联失败" />
    </section>
  );
}

function McpBindingAction({
  bound,
  disabled,
  loading,
  onChange,
}: {
  bound: boolean;
  disabled: boolean;
  loading: boolean;
  onChange: () => void;
}) {
  const button = (
    <Button
      danger={bound}
      disabled={disabled}
      loading={loading}
      onClick={bound ? undefined : onChange}
      size="small"
      type={bound ? "link" : "primary"}
    >
      {bound ? "取消关联" : "关联 MCP"}
    </Button>
  );

  if (!bound) return button;
  return (
    <Popconfirm
      cancelText="取消"
      description="取消后，该 Agent 将无法再调用此 MCP 服务提供的工具。"
      disabled={disabled}
      okButtonProps={{ danger: true }}
      okText="确认取消"
      onConfirm={onChange}
      title="确认取消 MCP 关联？"
    >
      {button}
    </Popconfirm>
  );
}
