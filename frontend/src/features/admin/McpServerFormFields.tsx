import { Alert, Button, Col, Form, Input, Radio, Row, Space } from "antd";
import type { FormInstance } from "antd";

import type { McpServerFormValues } from "@/features/admin/mcpServerForm";
import { McpToolPolicyEditor } from "@/features/admin/McpToolPolicyEditor";
import type { McpServer } from "@/shared/api/types";

type Props = {
  editing: boolean;
  form: FormInstance<McpServerFormValues>;
  server: McpServer | null;
  tenantId: string;
};

const HTTP_TRANSPORTS = new Set(["streamable_http", "sse"]);

export function McpServerFormFields({ editing, form, server, tenantId }: Props) {
  const transport = Form.useWatch("transport", form) ?? "streamable_http";
  const isStdio = transport === "stdio";
  const credentialTarget = isStdio ? "env" : "header";

  return (
    <>
      <Alert
        showIcon
        type="info"
        message="按协议填写连接信息；凭据会加密保存，接口不会返回实际值。"
        description={
          isStdio
            ? "STDIO 会在受控运行环境中启动本地进程；运行环境还必须显式启用 STDIO。"
            : "Streamable HTTP 和 SSE 连接远程 MCP 服务；生产环境必须使用 HTTPS。"
        }
      />
      <Row gutter={16}>
        <Col span={12}>
          <Form.Item name="name" label="配置名称" rules={[{ required: true }]}>
            <Input placeholder="例如：内部知识库" />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="transport" label="连接方式" rules={[{ required: true }]}>
            <Radio.Group optionType="button" buttonStyle="solid">
              <Radio.Button value="streamable_http">Streamable HTTP</Radio.Button>
              <Radio.Button value="sse">SSE</Radio.Button>
              <Radio.Button value="stdio">STDIO</Radio.Button>
            </Radio.Group>
          </Form.Item>
        </Col>
      </Row>
      <section className="admin-form-section">
        <h3>{isStdio ? "启动 MCP Server" : "连接 MCP Server"}</h3>
        <p>
          {isStdio
            ? "将启动命令与每一项命令参数分开填写，运行时会以受限环境启动该进程。"
            : "填写 MCP 服务的完整 URL；Streamable HTTP 与 SSE 均由运行时安全地建立连接。"}
        </p>
        <Form.Item
          name="endpoint"
          label={isStdio ? "命令" : "服务 URL"}
          rules={[{ required: true }]}
        >
          <Input placeholder={isStdio ? "例如：npx" : "例如：https://mcp.example.com/mcp"} />
        </Form.Item>
        {isStdio ? <McpArguments /> : null}
      </section>
      <McpCredentials editing={editing} target={credentialTarget} transport={transport} />
      <McpToolPolicyEditor form={form} server={server} tenantId={tenantId} />
      {editing ? <McpStatusField /> : null}
    </>
  );
}

function McpArguments() {
  return (
    <Form.List name="arguments">
      {(fields, { add, remove }) => (
        <Form.Item label="命令参数">
          {fields.map((field) => (
            <Space key={field.key} style={{ display: "flex", marginBottom: 8 }}>
              <Form.Item {...field} noStyle>
                <Input placeholder="例如：-y" />
              </Form.Item>
              <Button onClick={() => remove(field.name)}>移除</Button>
            </Space>
          ))}
          <Button onClick={() => add()}>添加命令参数</Button>
        </Form.Item>
      )}
    </Form.List>
  );
}

function McpCredentials({
  editing,
  target,
  transport,
}: {
  editing: boolean;
  target: "env" | "header";
  transport: string;
}) {
  const isStdio = target === "env";
  const label = isStdio ? "密钥环境变量" : "密钥请求头";
  const addLabel = isStdio ? "添加密钥环境变量" : "添加密钥请求头";
  const namePlaceholder = isStdio ? "例如：API_KEY" : "例如：Authorization";

  return (
    <section className="admin-form-section">
      <h3>{label}</h3>
      <p>
        {isStdio
          ? "变量值仅注入 MCP 子进程，Parrot 不会回显或以明文保存。"
          : "请求头值仅用于连接远程 MCP 服务，Parrot 不会回显或以明文保存。"}
      </p>
      <Form.List
        name="credentials"
        rules={[
          {
            validator: (_, value: unknown) => {
              const credentials = Array.isArray(value) ? value : [];
              if (credentials.every((item) => hasCredentialTarget(item, target))) {
                return Promise.resolve();
              }
              const protocol = HTTP_TRANSPORTS.has(transport) ? "HTTP/SSE" : "STDIO";
              return Promise.reject(
                new Error(`${protocol} 配置只允许使用${label}；请删除后重新添加不匹配的凭据。`),
              );
            },
          },
        ]}
      >
        {(fields, { add, remove }, { errors }) => (
          <>
            {fields.map((field) => (
              <Space key={field.key} wrap style={{ display: "flex", marginBottom: 8 }}>
                <Form.Item {...field} name={[field.name, "target"]} hidden initialValue={target}>
                  <Input />
                </Form.Item>
                <Form.Item
                  {...field}
                  name={[field.name, "name"]}
                  noStyle
                  rules={[{ required: true, message: `请输入${label}名称` }]}
                >
                  <Input placeholder={namePlaceholder} />
                </Form.Item>
                <Form.Item
                  {...field}
                  name={[field.name, "secret"]}
                  noStyle
                  rules={editing ? [] : [{ required: true, message: "请输入凭据值" }]}
                >
                  <Input.Password
                    autoComplete="new-password"
                    placeholder={editing ? "留空保留原值" : "输入凭据值"}
                  />
                </Form.Item>
                <Button onClick={() => remove(field.name)}>移除</Button>
              </Space>
            ))}
            <Button onClick={() => add({ target })}>{addLabel}</Button>
            <Form.ErrorList errors={errors} />
          </>
        )}
      </Form.List>
    </section>
  );
}

function hasCredentialTarget(value: unknown, expectedTarget: "env" | "header") {
  if (typeof value !== "object" || value === null) return false;
  return (value as Record<string, unknown>).target === expectedTarget;
}

function McpStatusField() {
  return (
    <Form.Item name="status" label="状态" rules={[{ required: true }]}>
      <Radio.Group optionType="button" buttonStyle="solid">
        <Radio.Button value="active">启用</Radio.Button>
        <Radio.Button value="disabled">停用</Radio.Button>
      </Radio.Group>
    </Form.Item>
  );
}
