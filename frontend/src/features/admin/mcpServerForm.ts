import type { McpServerCreate, McpServerUpdate } from "@/shared/api/types";

export type McpCredentialFormValue = {
  target: "env" | "header";
  name: string;
  secret?: string;
};

export type McpServerFormValues = Omit<McpServerCreate, "credentials"> & {
  credentials: McpCredentialFormValue[];
  status?: string;
};

export function toMcpServerCreatePayload(values: McpServerFormValues): McpServerCreate {
  return {
    name: values.name,
    transport: values.transport,
    endpoint: values.endpoint,
    arguments: values.arguments,
    credentials: values.credentials.map((item) => ({
      target: item.target,
      name: item.name,
      secret: item.secret ?? "",
    })),
    tool_policies: values.tool_policies ?? [],
  };
}

export function toMcpServerUpdatePayload(values: McpServerFormValues): McpServerUpdate {
  return {
    name: values.name,
    transport: values.transport,
    endpoint: values.endpoint,
    arguments: values.arguments,
    credentials: values.credentials.map(({ secret, ...item }) =>
      secret ? { ...item, secret } : item,
    ),
    status: values.status,
    tool_policies: values.tool_policies ?? [],
  };
}
