import { describe, expect, it } from "vitest";

import {
  toMcpServerCreatePayload,
  toMcpServerUpdatePayload,
  type McpServerFormValues,
} from "@/features/admin/mcpServerForm";

describe("MCP form payloads", () => {
  const values: McpServerFormValues = {
    name: "Docs",
    transport: "streamable_http",
    endpoint: "https://mcp.example.test",
    arguments: [],
    credentials: [{ target: "header", name: "Authorization" }],
    tool_policies: [],
    status: "active",
  };

  it("serializes a supplied value for a new credential", () => {
    expect(
      toMcpServerCreatePayload({
        ...values,
        credentials: [{ ...values.credentials[0], secret: "Bearer secret" }],
      }).credentials,
    ).toEqual([{ target: "header", name: "Authorization", secret: "Bearer secret" }]);
  });

  it("keeps an existing credential when no replacement value is supplied", () => {
    expect(toMcpServerUpdatePayload(values).credentials).toEqual([
      { target: "header", name: "Authorization" },
    ]);
  });
});
