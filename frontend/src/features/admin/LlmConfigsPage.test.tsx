import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App as AntdApp } from "antd";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { LlmConfigsPage } from "@/features/admin/LlmConfigsPage";
import { AuthContext, type AuthContextValue } from "@/shared/auth/AuthContext";
import { RequestErrorNotifier } from "@/shared/ui";
import { server } from "@/test/server";

const config = {
  id: "llm_test",
  tenant_id: "tenant_test",
  name: "Primary",
  provider: "openai-compatible",
  model: "model-test",
  base_url: "https://model.example.test/v1",
  credential_configured: true,
  temperature: 0.2,
  max_tokens: 4096,
  thinking_enabled: false,
  prompt_cache_enabled: false,
  status: "active",
  is_default: true,
};

const providers = [
  {
    key: "openai",
    name: "OpenAI",
    capabilities: [
      {
        kind: "llm",
        description: "OpenAI Chat Completions",
        credential_type: "api_key",
        default_base_url: "https://api.openai.com/v1",
        default_model: null,
        default_embedding_dimension: null,
        base_url_placeholder: null,
        model_placeholder: "例如：gpt-4.1-mini",
      },
      {
        kind: "embedding",
        description: "OpenAI Embeddings",
        credential_type: "api_key",
        default_base_url: "https://api.openai.com/v1",
        default_model: "text-embedding-3-large",
        default_embedding_dimension: 3072,
        base_url_placeholder: null,
        model_placeholder: null,
      },
    ],
  },
  {
    key: "volcengine_ark",
    name: "火山方舟（豆包）",
    capabilities: [
      {
        kind: "llm",
        description: "方舟 Chat Completions",
        credential_type: "api_key",
        default_base_url: "https://ark.cn-beijing.volces.com/api/v3",
        default_model: "doubao-seed-2-0-mini-260215",
        default_embedding_dimension: null,
        base_url_placeholder: null,
        model_placeholder: null,
      },
      {
        kind: "embedding",
        description: "方舟多模态向量",
        credential_type: "api_key",
        default_base_url: "https://ark.cn-beijing.volces.com/api/v3",
        default_model: "doubao-embedding-vision-251215",
        default_embedding_dimension: 2048,
        base_url_placeholder: null,
        model_placeholder: null,
      },
    ],
  },
  {
    key: "aliyun_bailian",
    name: "阿里云百炼",
    capabilities: [
      {
        kind: "reranker",
        description: "百炼 qwen3-rerank OpenAI 兼容扩展",
        credential_type: "api_key",
        default_base_url: null,
        default_model: "qwen3-rerank",
        default_embedding_dimension: null,
        base_url_placeholder:
          "例如：https://{业务空间ID}.cn-beijing.maas.aliyuncs.com/compatible-api/v1",
        model_placeholder: null,
      },
    ],
  },
];

const authValue: AuthContextValue = {
  session: {
    principal: {
      tenant_id: "tenant_test",
      subject_type: "user",
      subject_id: "user_test",
      username: "admin",
      display_name: "Administrator",
      avatar_present: false,
      permissions: ["llm_configs.read", "llm_configs.manage"],
      tenants: [{ id: "tenant_test", slug: "test", name: "Test Tenant" }],
      must_change_password: false,
      request_id: "req_test",
    },
    csrf_token: "csrf_test",
    expires_at: "2027-07-12T20:00:00Z",
    password_min_length: 12,
    default_schedule_timezone: "Asia/Shanghai",
  },
  loading: false,
  login: vi.fn(),
  logout: vi.fn(),
  refreshSession: vi.fn(),
  switchTenant: vi.fn(),
  hasPermission: (permission) => ["llm_configs.read", "llm_configs.manage"].includes(permission),
};

function renderPage() {
  server.use(
    http.get("/api/v1/admin/tenants/tenant_test/model-providers", () =>
      HttpResponse.json({ code: "OK", message: "success", data: providers, request_id: "req" }),
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <AntdApp>
      <QueryClientProvider client={client}>
        <RequestErrorNotifier />
        <MemoryRouter>
          <AuthContext.Provider value={authValue}>
            <LlmConfigsPage />
          </AuthContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>
    </AntdApp>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("LlmConfigsPage", () => {
  it("lets an administrator explicitly enable thinking mode", async () => {
    const user = userEvent.setup();
    let updateBody: unknown;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/llm-configs", () =>
        HttpResponse.json({ code: "OK", message: "success", data: [config], request_id: "req" }),
      ),
      http.patch("/api/v1/admin/tenants/tenant_test/llm-configs/llm_test", async ({ request }) => {
        updateBody = await request.json();
        return HttpResponse.json({
          code: "OK",
          message: "success",
          data: { ...config, thinking_enabled: true },
          request_id: "req_update",
        });
      }),
    );
    renderPage();

    const row = (await screen.findByText("Primary")).closest("tr");
    if (!(row instanceof HTMLTableRowElement)) throw new Error("Expected LLM table row");
    expect(within(row).getAllByText("未开启")).toHaveLength(2);
    await user.click(within(row).getByRole("button", { name: "编辑" }));
    const dialog = screen.getByRole("dialog", { name: "编辑模型配置" });
    const thinkingSwitch = within(dialog).getByRole("switch", { name: "启用模型思考模式" });
    expect(thinkingSwitch).not.toBeChecked();
    expect(within(dialog).getByRole("switch", { name: "启用 Prompt Cache" })).not.toBeChecked();

    await user.click(thinkingSwitch);
    await user.click(within(dialog).getByRole("button", { name: /确.*定/ }));

    await waitFor(() => expect(updateBody).toMatchObject({ thinking_enabled: true }));
  });

  it("tests the edited LLM draft from the modal without resending the saved credential", async () => {
    const user = userEvent.setup();
    let requestBody = "not-called";
    let releaseResponse: () => void = () => undefined;
    const responseGate = new Promise<void>((resolve) => {
      releaseResponse = resolve;
    });
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/llm-configs", () =>
        HttpResponse.json({ code: "OK", message: "success", data: [config], request_id: "req" }),
      ),
      http.post(
        "/api/v1/admin/tenants/tenant_test/llm-configs/connection-test",
        async ({ request }) => {
          requestBody = await request.text();
          await responseGate;
          return HttpResponse.json({
            code: "OK",
            message: "success",
            data: { connected: true },
            request_id: "req_test_connection",
          });
        },
      ),
    );
    renderPage();

    const row = (await screen.findByText("Primary")).closest("tr");
    if (!(row instanceof HTMLTableRowElement)) throw new Error("Expected LLM table row");
    expect(within(row).queryByRole("button", { name: "测试连接" })).not.toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "编辑" }));
    const dialog = screen.getByRole("dialog", { name: "编辑模型配置" });
    const testButton = within(dialog).getByRole("button", { name: "测试连接" });
    await user.click(testButton);

    await waitFor(() => expect(testButton).toBeDisabled());
    expect(testButton).toHaveClass("ant-btn-loading");
    releaseResponse();

    expect(await screen.findByText("连接测试通过")).toBeInTheDocument();
    expect(JSON.parse(requestBody)).toMatchObject({
      config_id: "llm_test",
      provider: "openai-compatible",
      model: "model-test",
      base_url: "https://model.example.test/v1",
    });
    expect(JSON.parse(requestBody)).not.toHaveProperty("api_key");
  });

  it("shows structured provider diagnostics when a connection test fails", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/llm-configs", () =>
        HttpResponse.json({ code: "OK", message: "success", data: [config], request_id: "req" }),
      ),
      http.post("/api/v1/admin/tenants/tenant_test/llm-configs/connection-test", () =>
        HttpResponse.json(
          {
            code: "MODEL_CONFIG_CONNECTION_FAILED",
            message: "连接测试未通过，请检查服务地址、模型和凭据后重试。",
            details: [
              { field: "upstream_http_status", reason: "401 Unauthorized" },
              { field: "upstream_error_code", reason: "Unauthorized" },
              { field: "upstream_message", reason: "Invalid API key" },
              { field: "upstream_request_id", reason: "provider_req_123" },
            ],
            request_id: "req_connection_failed",
          },
          { status: 502 },
        ),
      ),
    );
    renderPage();

    const row = (await screen.findByText("Primary")).closest("tr");
    if (!(row instanceof HTMLTableRowElement)) throw new Error("Expected LLM table row");
    await user.click(within(row).getByRole("button", { name: "编辑" }));
    const dialog = screen.getByRole("dialog", { name: "编辑模型配置" });
    await user.click(within(dialog).getByRole("button", { name: "测试连接" }));

    expect(await within(dialog).findByText("Invalid API key")).toBeInTheDocument();
    expect(within(dialog).getByText("供应商错误信息：")).toBeInTheDocument();
    expect(within(dialog).getByText("401 Unauthorized")).toBeInTheDocument();
    expect(within(dialog).getByText("provider_req_123")).toBeInTheDocument();
    expect(within(dialog).getByText("Parrot 请求编号：req_connection_failed")).toBeInTheDocument();
  });

  it("tests the saved Embedding configuration from the same model page", async () => {
    const user = userEvent.setup();
    let called = false;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/llm-configs", () =>
        HttpResponse.json({ code: "OK", message: "success", data: [config], request_id: "req" }),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/embedding-configs", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: [
            {
              id: "embedding_test",
              tenant_id: "tenant_test",
              name: "Knowledge Embedding",
              provider: "openai_compatible",
              model: "text-embedding-v4",
              base_url: "https://embedding.example.test/v1",
              credential_configured: true,
              embedding_dimension: 1024,
              configuration_version: 1,
              status: "active",
              reference_count: 0,
              can_delete: true,
            },
          ],
          request_id: "req_embedding",
        }),
      ),
      http.post("/api/v1/admin/tenants/tenant_test/embedding-configs/connection-test", () => {
        called = true;
        return HttpResponse.json({
          code: "OK",
          message: "success",
          data: { connected: true },
          request_id: "req_test_connection",
        });
      }),
    );
    renderPage();

    await user.click(screen.getByRole("tab", { name: "Embedding" }));
    const row = (await screen.findByText("Knowledge Embedding")).closest("tr");
    if (!(row instanceof HTMLTableRowElement)) throw new Error("Expected Embedding table row");
    await user.click(within(row).getByRole("button", { name: "编辑" }));
    const dialog = screen.getByRole("dialog", { name: "编辑Embedding 配置" });
    await user.click(within(dialog).getByRole("button", { name: "测试连接" }));

    await waitFor(() => expect(called).toBe(true));
    expect(await screen.findByText("连接测试通过")).toBeInTheDocument();
  });

  it("fills provider-owned defaults when creating a Doubao LLM configuration", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/llm-configs", () =>
        HttpResponse.json({ code: "OK", message: "success", data: [], request_id: "req" }),
      ),
    );
    renderPage();

    await user.click(await screen.findByRole("button", { name: "新建" }));
    const dialog = screen.getByRole("dialog", { name: "新建模型配置" });
    const providerSelect = within(dialog).getByRole("combobox", { name: "供应商" });
    await user.click(providerSelect);
    await user.click(await screen.findByText("火山方舟（豆包）"));

    expect(within(dialog).getByRole("textbox", { name: "模型" })).toHaveValue(
      "doubao-seed-2-0-mini-260215",
    );
    expect(within(dialog).getByRole("textbox", { name: "服务地址" })).toHaveValue(
      "https://ark.cn-beijing.volces.com/api/v3",
    );
  });

  it("creates and tests a Bailian reranker draft with provider-owned defaults", async () => {
    const user = userEvent.setup();
    let requestBody: unknown;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/llm-configs", () =>
        HttpResponse.json({ code: "OK", message: "success", data: [], request_id: "req" }),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/reranker-configs", () =>
        HttpResponse.json({ code: "OK", message: "success", data: [], request_id: "req" }),
      ),
      http.post(
        "/api/v1/admin/tenants/tenant_test/reranker-configs/connection-test",
        async ({ request }) => {
          requestBody = await request.json();
          return HttpResponse.json({
            code: "OK",
            message: "success",
            data: { connected: true },
            request_id: "req_reranker_test",
          });
        },
      ),
    );
    renderPage();

    await user.click(screen.getByRole("tab", { name: "重排序" }));
    expect(screen.queryByText(/暂不提供独立重排序能力/)).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "新建" }));
    const dialog = screen.getByRole("dialog", { name: "新建重排序 配置" });

    expect(within(dialog).getByRole("textbox", { name: "模型" })).toHaveValue("qwen3-rerank");
    expect(within(dialog).getByRole("textbox", { name: "服务地址" })).toHaveValue("");
    expect(within(dialog).getByRole("textbox", { name: "服务地址" })).toHaveAttribute(
      "placeholder",
      "例如：https://{业务空间ID}.cn-beijing.maas.aliyuncs.com/compatible-api/v1",
    );
    await user.type(within(dialog).getByLabelText("名称"), "Bailian Reranker");
    await user.type(
      within(dialog).getByRole("textbox", { name: "服务地址" }),
      "https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1",
    );
    await user.type(within(dialog).getByLabelText("API Key"), "test-api-key");
    await user.click(within(dialog).getByRole("button", { name: "测试连接" }));

    expect(await screen.findByText("连接测试通过")).toBeInTheDocument();
    expect(requestBody).toMatchObject({
      provider: "aliyun_bailian",
      model: "qwen3-rerank",
      base_url: "https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1",
      api_key: "test-api-key",
    });
    expect(requestBody).not.toHaveProperty("access_key_id");
    expect(requestBody).not.toHaveProperty("secret_access_key");
  });
});
