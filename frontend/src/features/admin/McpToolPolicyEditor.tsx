import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Form, Select, Space, Switch, Table, Tag, Tooltip, Typography } from "antd";
import type { FormInstance } from "antd";

import type { McpServerFormValues } from "@/features/admin/mcpServerForm";
import { adminApi } from "@/shared/api/client";
import type { McpDiscoveredTool, McpServer, McpToolPolicy } from "@/shared/api/types";
import { RequestErrorAlert } from "@/shared/ui";

type PolicyChoice = "automatic_read" | "required_read" | "required_write" | "forbidden";

type Props = {
  form: FormInstance<McpServerFormValues>;
  server: McpServer | null;
  tenantId: string;
};

const POLICY_OPTIONS = [
  { value: "automatic_read", label: "查询数据（自动执行）" },
  { value: "required_read", label: "查询敏感数据（执行前确认）" },
  { value: "required_write", label: "变更或发送数据（执行前确认）" },
  { value: "forbidden", label: "禁止 Agent 使用" },
];

export function McpToolPolicyEditor({ form, server, tenantId }: Props) {
  const [tools, setTools] = useState<McpDiscoveredTool[]>([]);
  const policies = Form.useWatch("tool_policies", form) ?? [];
  const discovery = useMutation({
    mutationFn: () => adminApi.discoverMcpTools(tenantId, server?.id ?? ""),
    onSuccess: (discovered) => {
      setTools(discovered);
      form.setFieldValue(
        "tool_policies",
        policies.filter((policy) => policyMatchesDiscovery(policy, server, discovered)),
      );
    },
  });

  useEffect(() => {
    setTools(
      (server?.tool_policies ?? []).map((policy) => ({
        name: policy.name,
        description: policy.description,
        input_schema: policy.input_schema,
        schema_hash: policy.schema_hash,
        read_only_hint: false,
      })),
    );
  }, [server]);

  if (!server) {
    return (
      <Alert
        showIcon
        type="info"
        message="保存连接后设置 Agent 使用权限"
        description="保存后连接 MCP 服务并读取工具参数，再决定查询是否自动执行，以及哪些操作必须先让用户确认。"
      />
    );
  }

  return (
    <section className="admin-form-section">
      <Space align="start">
        <div>
          <h3>Agent 使用权限</h3>
          <p>
            知识型和功能型 Agent
            都会遵循这里的权限。创建、修改、删除或发送数据必须先让用户确认；服务声明仅作风险参考。
          </p>
        </div>
        <Button loading={discovery.isPending} onClick={() => discovery.mutate()}>
          连接并刷新工具
        </Button>
      </Space>
      <RequestErrorAlert error={discovery.error} fallback="读取 MCP 工具失败" />
      <Form.Item name="tool_policies" hidden>
        <PolicyValueField />
      </Form.Item>
      <Table<McpDiscoveredTool>
        rowKey="name"
        size="small"
        pagination={false}
        dataSource={tools}
        locale={{ emptyText: "点击“连接并刷新工具”读取可配置工具" }}
        columns={[
          {
            title: "工具",
            render: (_, tool) => (
              <Space direction="vertical" size={0}>
                <Typography.Text strong>{tool.name}</Typography.Text>
                <Typography.Text type="secondary">{tool.description || "暂无说明"}</Typography.Text>
              </Space>
            ),
          },
          {
            title: "服务声明",
            width: 130,
            render: (_, tool) =>
              tool.read_only_hint ? <Tag color="blue">声明为查询</Tag> : <Tag>未声明用途</Tag>,
          },
          {
            title: "Agent 使用权限",
            width: 270,
            render: (_, tool) => (
              <Select
                aria-label={`${tool.name} Agent 使用权限`}
                allowClear
                placeholder="未配置（Agent 不可使用）"
                options={POLICY_OPTIONS}
                value={choiceFor(policies.find((item) => item.name === tool.name))}
                onChange={(choice: PolicyChoice | undefined) =>
                  updatePolicy(form, policies, tool, choice)
                }
              />
            ),
          },
          {
            title: "并行执行",
            width: 110,
            render: (_, tool) => {
              const policy = policies.find((item) => item.name === tool.name);
              const enabled = policy?.effect === "read" && policy.approval === "automatic";
              return (
                <Tooltip
                  title={enabled ? "仅在服务端确认工具可安全并发时开启" : "仅自动查询可配置并行"}
                >
                  <span>
                    <Switch
                      aria-label={`${tool.name} 允许并行执行`}
                      size="small"
                      checked={policy?.parallel_safe ?? false}
                      disabled={!enabled}
                      onChange={(checked) => updateParallelSafe(form, policies, tool.name, checked)}
                    />
                  </span>
                </Tooltip>
              );
            },
          },
        ]}
      />
    </section>
  );
}

function updatePolicy(
  form: FormInstance<McpServerFormValues>,
  policies: McpToolPolicy[],
  tool: McpDiscoveredTool,
  choice: PolicyChoice | undefined,
) {
  const next = policies.filter((item) => item.name !== tool.name);
  if (choice) next.push(policyFromChoice(tool, choice));
  form.setFieldValue("tool_policies", next);
}

function policyFromChoice(tool: McpDiscoveredTool, choice: PolicyChoice): McpToolPolicy {
  const effect = choice === "automatic_read" || choice === "required_read" ? "read" : "side_effect";
  const approval =
    choice === "automatic_read" ? "automatic" : choice === "forbidden" ? "forbidden" : "required";
  return {
    name: tool.name,
    description: tool.description,
    input_schema: tool.input_schema,
    effect,
    approval,
    parallel_safe: false,
  };
}

function updateParallelSafe(
  form: FormInstance<McpServerFormValues>,
  policies: McpToolPolicy[],
  toolName: string,
  checked: boolean,
) {
  form.setFieldValue(
    "tool_policies",
    policies.map((policy) =>
      policy.name === toolName ? { ...policy, parallel_safe: checked } : policy,
    ),
  );
}

function choiceFor(policy: McpToolPolicy | undefined): PolicyChoice | undefined {
  if (!policy) return undefined;
  if (policy.approval === "forbidden") return "forbidden";
  if (policy.effect === "read" && policy.approval === "automatic") return "automatic_read";
  return policy.effect === "read" ? "required_read" : "required_write";
}

function policyMatchesDiscovery(
  policy: McpToolPolicy,
  server: McpServer | null,
  tools: McpDiscoveredTool[],
) {
  const stored = server?.tool_policies.find((item) => item.name === policy.name);
  const discovered = tools.find((item) => item.name === policy.name);
  return Boolean(
    discovered &&
    (stored
      ? stored.schema_hash === discovered.schema_hash
      : JSON.stringify(policy.input_schema) === JSON.stringify(discovered.input_schema)),
  );
}

function PolicyValueField() {
  return null;
}
