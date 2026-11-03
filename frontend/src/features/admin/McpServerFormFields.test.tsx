import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Form } from "antd";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { McpServerFormFields } from "@/features/admin/McpServerFormFields";
import type { McpServerFormValues } from "@/features/admin/mcpServerForm";

describe("McpServerFormFields", () => {
  it("shows HTTP connection fields first and switches to STDIO-specific fields", async () => {
    const user = userEvent.setup();
    render(<McpFormHarness />);

    expect(screen.getByText("连接 MCP Server")).toBeInTheDocument();
    expect(screen.getByLabelText("服务 URL")).toBeInTheDocument();
    expect(screen.getByText("密钥请求头")).toBeInTheDocument();
    expect(screen.queryByText("命令参数")).not.toBeInTheDocument();

    await user.click(screen.getByText("STDIO").closest("label") as HTMLLabelElement);

    expect(screen.getByText("启动 MCP Server")).toBeInTheDocument();
    expect(screen.getByLabelText("命令")).toBeInTheDocument();
    expect(screen.getByText("命令参数")).toBeInTheDocument();
    expect(screen.getByText("密钥环境变量")).toBeInTheDocument();
  });
});

function McpFormHarness() {
  const [form] = Form.useForm<McpServerFormValues>();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <Form
        form={form}
        initialValues={{ arguments: [], credentials: [], transport: "streamable_http" }}
      >
        <McpServerFormFields editing={false} form={form} server={null} tenantId="tenant_test" />
      </Form>
    </QueryClientProvider>
  );
}
