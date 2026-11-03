import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Button, Form } from "antd";
import type { FormInstance } from "antd";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { McpServerFormValues } from "@/features/admin/mcpServerForm";
import { McpToolPolicyEditor } from "@/features/admin/McpToolPolicyEditor";
import { adminApi } from "@/shared/api/client";
import type { McpServer, McpToolPolicy } from "@/shared/api/types";

const discovered = {
  name: "search_docs",
  description: "Search approved documentation",
  input_schema: { type: "object", properties: { query: { type: "string" } } },
  schema_hash: "sha256:new",
  read_only_hint: true,
};

describe("McpToolPolicyEditor", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("requires an explicit administrator policy after discovery", async () => {
    const user = userEvent.setup();
    const inspect = vi.fn();
    vi.spyOn(adminApi, "discoverMcpTools").mockResolvedValue([discovered]);
    render(<PolicyHarness server={mcpServer([])} onInspect={inspect} />);

    expect(screen.getByText(/知识型和功能型 Agent/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "连接并刷新工具" }));
    await user.click(await screen.findByRole("combobox", { name: "search_docs Agent 使用权限" }));
    await user.click(screen.getByText("查询数据（自动执行）"));
    await user.click(screen.getByRole("button", { name: "检查策略" }));

    expect(inspect).toHaveBeenCalledWith([
      {
        name: "search_docs",
        description: "Search approved documentation",
        input_schema: discovered.input_schema,
        effect: "read",
        approval: "automatic",
        parallel_safe: false,
      },
    ]);
  });

  it("maps data-changing access to explicit confirmation", async () => {
    const user = userEvent.setup();
    const inspect = vi.fn();
    vi.spyOn(adminApi, "discoverMcpTools").mockResolvedValue([discovered]);
    render(<PolicyHarness server={mcpServer([])} onInspect={inspect} />);

    await user.click(screen.getByRole("button", { name: "连接并刷新工具" }));
    await user.click(await screen.findByRole("combobox", { name: "search_docs Agent 使用权限" }));
    await user.click(screen.getByText("变更或发送数据（执行前确认）"));
    await user.click(screen.getByRole("button", { name: "检查策略" }));

    expect(inspect).toHaveBeenCalledWith([
      {
        name: "search_docs",
        description: "Search approved documentation",
        input_schema: discovered.input_schema,
        effect: "side_effect",
        approval: "required",
        parallel_safe: false,
      },
    ]);
  });

  it("removes a saved policy when live discovery reports schema drift", async () => {
    const user = userEvent.setup();
    const inspect = vi.fn();
    const policy: McpToolPolicy & { schema_hash: string } = {
      name: "search_docs",
      description: "Search approved documentation",
      input_schema: { type: "object" },
      schema_hash: "sha256:old",
      effect: "read",
      approval: "automatic",
      parallel_safe: false,
    };
    vi.spyOn(adminApi, "discoverMcpTools").mockResolvedValue([discovered]);
    render(<PolicyHarness server={mcpServer([policy])} onInspect={inspect} />);

    await user.click(screen.getByRole("button", { name: "连接并刷新工具" }));
    await screen.findByRole("combobox", { name: "search_docs Agent 使用权限" });
    await user.click(screen.getByRole("button", { name: "检查策略" }));

    expect(inspect).toHaveBeenCalledWith([]);
  });

  it("requires an explicit parallel-safe opt-in for automatic reads", async () => {
    const user = userEvent.setup();
    const inspect = vi.fn();
    vi.spyOn(adminApi, "discoverMcpTools").mockResolvedValue([discovered]);
    render(<PolicyHarness server={mcpServer([])} onInspect={inspect} />);

    await user.click(screen.getByRole("button", { name: "连接并刷新工具" }));
    await user.click(await screen.findByRole("combobox", { name: "search_docs Agent 使用权限" }));
    await user.click(screen.getByText("查询数据（自动执行）"));
    await user.click(screen.getByRole("switch", { name: "search_docs 允许并行执行" }));
    await user.click(screen.getByRole("button", { name: "检查策略" }));

    expect(inspect).toHaveBeenCalledWith([
      expect.objectContaining({ name: "search_docs", parallel_safe: true }),
    ]);
  });
});

function PolicyHarness({
  server,
  onInspect,
}: {
  server: McpServer;
  onInspect: (policies: McpToolPolicy[]) => void;
}) {
  const [form] = Form.useForm<McpServerFormValues>();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <Form form={form} initialValues={{ tool_policies: withoutHashes(server) }}>
        <McpToolPolicyEditor form={form} server={server} tenantId="tenant_test" />
        <PolicyInspectButton form={form} onInspect={onInspect} />
      </Form>
    </QueryClientProvider>
  );
}

function PolicyInspectButton({
  form,
  onInspect,
}: {
  form: FormInstance<McpServerFormValues>;
  onInspect: (policies: McpToolPolicy[]) => void;
}) {
  const policies = Form.useWatch("tool_policies", form);
  return <Button onClick={() => onInspect(policies ?? [])}>检查策略</Button>;
}

function withoutHashes(server: McpServer): McpToolPolicy[] {
  return server.tool_policies.map((policy) => ({
    name: policy.name,
    description: policy.description,
    input_schema: policy.input_schema,
    effect: policy.effect,
    approval: policy.approval,
    parallel_safe: policy.parallel_safe,
  }));
}

function mcpServer(toolPolicies: McpServer["tool_policies"]): McpServer {
  return {
    id: "mcp_docs",
    tenant_id: "tenant_test",
    name: "Docs",
    transport: "streamable_http",
    endpoint: "https://mcp.example.test",
    arguments: [],
    credentials: [],
    status: "active",
    tool_policies: toolPolicies,
    bound_agents: [],
  };
}
