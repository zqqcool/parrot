import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App as AntdApp } from "antd";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { KnowledgeDocumentsPage } from "@/features/admin/KnowledgeDocumentsPage";
import { KnowledgePage } from "@/features/admin/KnowledgePage";
import { KnowledgeRetrievalPage } from "@/features/admin/KnowledgeRetrievalPage";
import { KnowledgeSpaceCreatePage } from "@/features/admin/KnowledgeSpaceCreateWizard";
import { AuthContext, type AuthContextValue } from "@/shared/auth/AuthContext";
import { RequestErrorNotifier } from "@/shared/ui";
import { server } from "@/test/server";

const space = {
  id: "space_engineering",
  tenant_id: "tenant_test",
  slug: "engineering",
  name: "Engineering",
  classification: "standard",
  status: "active",
  chunk_separator: "\\n\\n",
  chunk_size_chars: 4000,
  chunk_overlap_chars: 200,
  text_processing: {
    normalize_whitespace: false,
    remove_urls_and_emails: false,
  },
  embedding_config_id: null,
  embedding_config_provider: null,
  embedding_config_model: null,
  embedding_config_base_url: null,
  embedding_config_dimension: null,
  embedding_config_version: null,
  candidate_top_k: 20,
  min_vector_score: null,
  rerank_enabled: false,
  reranker_config_id: null,
  rerank_top_n: 10,
  min_rerank_score: null,
  retrieval_index_revision: 1,
  retrieval_index_status: "not_configured",
  access_revision: 2,
  created_at: "2026-07-14T01:00:00Z",
  updated_at: "2026-07-14T01:00:00Z",
};

const embedding = {
  id: "embedding_test",
  tenant_id: "tenant_test",
  name: "Production embedding",
  provider: "openai_compatible",
  model: "text-embedding-3-large",
  base_url: "https://models.example.test/v1",
  embedding_dimension: 1024,
  credential_configured: true,
  status: "active",
  created_at: "2026-07-14T01:00:00Z",
  updated_at: "2026-07-14T01:00:00Z",
};

const ok = (data: unknown) =>
  HttpResponse.json({ code: "OK", message: "success", data, request_id: "req_test" });

function authValue(permissions: string[]): AuthContextValue {
  return {
    session: {
      principal: {
        tenant_id: "tenant_test",
        subject_type: "user",
        subject_id: "user_test",
        username: "admin",
        display_name: "Administrator",
        avatar_present: false,
        permissions,
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
    hasPermission: (permission) => permissions.includes(permission),
  };
}

function renderKnowledgePage(
  permissions = [
    "knowledge.spaces.read",
    "knowledge.spaces.manage",
    "knowledge.documents.read",
    "knowledge.documents.manage",
    "llm_configs.read",
  ],
  initialEntry = "/admin/knowledge",
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <AntdApp>
      <QueryClientProvider client={client}>
        <RequestErrorNotifier />
        <MemoryRouter initialEntries={[initialEntry]}>
          <AuthContext.Provider value={authValue(permissions)}>
            <Routes>
              <Route path="/admin/knowledge" element={<KnowledgePage />} />
              <Route path="/admin/knowledge/new" element={<KnowledgeSpaceCreatePage />} />
              <Route
                path="/admin/knowledge/:spaceId/documents"
                element={<KnowledgeDocumentsPage />}
              />
              <Route
                path="/admin/knowledge/:spaceId/retrieval"
                element={<KnowledgeRetrievalPage />}
              />
            </Routes>
          </AuthContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>
    </AntdApp>,
  );
}

function renderKnowledgeDocumentsPage(
  permissions = [
    "knowledge.spaces.read",
    "knowledge.spaces.manage",
    "knowledge.documents.read",
    "knowledge.documents.manage",
  ],
) {
  renderKnowledgePage(permissions, "/admin/knowledge/space_engineering/documents");
}

beforeEach(() => {
  server.use(
    http.get(
      "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/ingestions",
      () => ok([]),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/knowledge/merge-settings", () =>
      ok({
        tenant_id: "tenant_test",
        merge_rerank_enabled: false,
        reranker_config_id: null,
        rerank_top_n: 20,
        result_top_k: 6,
        min_rerank_score: null,
        policy: {
          minimum_space_hits: 2,
          per_space_candidate_cap: 12,
          rerank_top_n_min: 1,
          rerank_top_n_max: 60,
          result_top_k_min: 1,
          result_top_k_max: 12,
          min_rerank_score_min: 0,
          min_rerank_score_max: 1,
        },
        updated_at: null,
      }),
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("KnowledgePage", () => {
  it("summarizes each knowledge space's retrieval configuration", async () => {
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () =>
        ok([
          {
            ...space,
            embedding_config_id: "embedding_test",
            embedding_config_model: "text-embedding-v4",
            embedding_config_dimension: 1024,
            candidate_top_k: 30,
            rerank_enabled: true,
            retrieval_index_status: "pending",
          },
        ]),
      ),
    );
    renderKnowledgePage();

    expect(await screen.findByRole("columnheader", { name: "检索策略" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Embedding" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "索引状态" })).toBeInTheDocument();
    expect(await screen.findByText("向量策略（待就绪）")).toBeInTheDocument();
    expect(screen.getByText("text-embedding-v4")).toBeInTheDocument();
    expect(screen.getByText("1024 维")).toBeInTheDocument();
    expect(screen.getByText("等待索引")).toBeInTheDocument();
    expect(screen.getByText("30")).toBeInTheDocument();
    expect(await screen.findByText("合并重排：关")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "多库合并配置" })).toBeInTheDocument();
  });

  it("creates a tenant knowledge space with the shared API client", async () => {
    const user = userEvent.setup();
    let payload: unknown;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([])),
      http.get("/api/v1/admin/tenants/tenant_test/embedding-configs", () => ok([embedding])),
      http.get(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/documents",
        () => ok([]),
      ),
      http.post("/api/v1/admin/tenants/tenant_test/knowledge/spaces", async ({ request }) => {
        payload = await request.json();
        return ok(space);
      }),
    );
    renderKnowledgePage();

    await screen.findByText("当前账号暂无可管理的知识库");
    expect(screen.queryByRole("heading", { name: "开始构建知识库" })).not.toBeInTheDocument();
    const createButton = screen.getByRole("button", { name: "新建知识库" });
    expect(createButton.closest(".parrot-search-bar-actions")).toBeInTheDocument();
    await user.click(createButton);
    expect(await screen.findByRole("heading", { name: "配置知识库" })).toBeInTheDocument();
    expect(screen.queryByText("工作台", { selector: ".ant-breadcrumb" })).not.toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "显示名称" }), "Engineering");
    expect(screen.queryByRole("textbox", { name: "唯一标识" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "下一步" }));
    const separator = screen.getByRole("textbox", { name: "分段标识符" });
    expect(separator).toHaveValue("\\n\\n");
    await user.clear(separator);
    await user.type(separator, "***");
    await user.click(screen.getByRole("radio", { name: /高质量：向量/ }));
    expect(screen.getByText(/选择 Embedding 不会启用部署级向量检索运行时/)).toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Embedding 配置" }));
    await user.click(await screen.findByText(/Production embedding/));
    const whitespace = screen.getByRole("checkbox", { name: /规整多余空白/ });
    const removeAddresses = screen.getByRole("checkbox", { name: /移除 URL 和邮箱/ });
    expect(whitespace).not.toBeChecked();
    expect(removeAddresses).not.toBeChecked();
    await user.click(whitespace);
    await user.click(removeAddresses);
    await user.click(screen.getByRole("button", { name: "创建并进入上传" }));

    await waitFor(() =>
      expect(payload).toEqual({
        name: "Engineering",
        classification: "standard",
        chunk_separator: "***",
        chunk_size_chars: 4000,
        chunk_overlap_chars: 200,
        embedding_config_id: "embedding_test",
        text_processing: {
          normalize_whitespace: true,
          remove_urls_and_emails: true,
        },
      }),
    );
    expect(await screen.findByRole("heading", { name: "上传资料" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上传文件" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "录入文本" })).toBeInTheDocument();
  });

  it("deletes an empty knowledge space after confirmation", async () => {
    const user = userEvent.setup();
    let deletedSpaceId = "";
    let spaces = [space];
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok(spaces)),
      http.delete("/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering", () => {
        deletedSpaceId = space.id;
        spaces = [];
        return ok(null);
      }),
    );
    renderKnowledgePage();

    await user.click(await screen.findByRole("button", { name: "删除" }));
    expect(await screen.findByText("删除知识库“Engineering”？")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() => expect(deletedSpaceId).toBe(space.id));
    expect(await screen.findByText("当前账号暂无可管理的知识库")).toBeInTheDocument();
  });

  it("hides knowledge space deletion without management permission", async () => {
    server.use(http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([space])));
    renderKnowledgePage(["knowledge.spaces.read", "knowledge.documents.read"]);

    expect(await screen.findByText("Engineering")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删除" })).not.toBeInTheDocument();
  });

  it("hides merge configuration without model configuration visibility", async () => {
    server.use(http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([space])));
    renderKnowledgePage(["knowledge.spaces.read", "knowledge.spaces.manage"]);

    expect(await screen.findByText("合并重排：关")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "多库合并配置" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建知识库" })).toBeInTheDocument();
  });

  it("explains why a non-empty knowledge space cannot be deleted", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([space])),
      http.delete("/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering", () =>
        HttpResponse.json(
          {
            code: "KNOWLEDGE_SPACE_NOT_EMPTY",
            message: "知识库仍包含文档、上传源或智能体关联，无法删除。",
            details: [
              { field: "documents", reason: "1" },
              { field: "sources", reason: "1" },
            ],
            request_id: "req_conflict",
          },
          { status: 409 },
        ),
      ),
    );
    renderKnowledgePage();

    await user.click(await screen.findByRole("button", { name: "删除" }));
    await user.click(screen.getByRole("button", { name: "确认删除" }));

    expect(
      await screen.findByText("知识库仍包含文档、上传源或智能体关联，无法删除。"),
    ).toBeInTheDocument();
    expect(screen.getByText("Engineering")).toBeInTheDocument();
  });

  it("updates default chunking before later uploads", async () => {
    const user = userEvent.setup();
    let payload: unknown;
    const updated = { ...space, chunk_size_chars: 2400, chunk_overlap_chars: 240 };
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([space])),
      http.get(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/documents",
        () => ok([]),
      ),
      http.patch(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/chunking",
        async ({ request }) => {
          payload = await request.json();
          return ok(updated);
        },
      ),
    );
    renderKnowledgeDocumentsPage();

    const chunkingButton = await screen.findByRole("button", { name: "调整切分配置" });
    expect(chunkingButton).toHaveClass("ant-btn-primary", "ant-btn-background-ghost");
    await user.click(chunkingButton);
    const dialog = await screen.findByRole("dialog", { name: "调整切分配置" });
    await user.clear(within(dialog).getByRole("spinbutton", { name: "单块目标字符数" }));
    await user.type(within(dialog).getByRole("spinbutton", { name: "单块目标字符数" }), "2400");
    await user.clear(within(dialog).getByRole("spinbutton", { name: "相邻块重叠字符数" }));
    await user.type(within(dialog).getByRole("spinbutton", { name: "相邻块重叠字符数" }), "240");
    await user.click(within(dialog).getByRole("button", { name: "OK" }));

    await waitFor(() =>
      expect(payload).toEqual({
        chunk_size_chars: 2400,
        chunk_overlap_chars: 240,
        chunk_separator: "\\n\\n",
        text_processing: {
          normalize_whitespace: false,
          remove_urls_and_emails: false,
        },
      }),
    );
    expect(await screen.findByText("2,400 字符")).toBeInTheDocument();
  });

  it("shows retrieval settings on the retrieval page and initializes its fields", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const vectorSpace = {
      ...space,
      embedding_config_id: embedding.id,
      embedding_config_model: embedding.model,
      embedding_config_dimension: embedding.embedding_dimension,
      candidate_top_k: 30,
    };
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([vectorSpace])),
      http.get(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/documents",
        () => ok([]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/reranker-configs", () => ok([])),
    );
    renderKnowledgePage(
      [
        "knowledge.spaces.read",
        "knowledge.spaces.manage",
        "knowledge.documents.read",
        "knowledge.documents.manage",
        "knowledge.query",
      ],
      "/admin/knowledge/space_engineering/retrieval",
    );

    const queryPanel = await screen.findByRole("complementary", { name: "查询文本" });
    expect(within(queryPanel).getByRole("heading", { name: "检索参数" })).toBeInTheDocument();
    expect(within(queryPanel).getByRole("spinbutton", { name: "候选 Top K" })).toHaveValue("30");
    expect(screen.queryByRole("dialog", { name: "调整检索参数" })).not.toBeInTheDocument();
    expect(consoleError).not.toHaveBeenCalledWith(
      expect.stringContaining("Instance created by `useForm` is not connected"),
    );
  });

  it("saves the retrieval test candidate limit on the knowledge space", async () => {
    const user = userEvent.setup();
    let payload: unknown;
    const vectorSpace = {
      ...space,
      embedding_config_id: embedding.id,
      embedding_config_model: embedding.model,
      embedding_config_dimension: embedding.embedding_dimension,
      candidate_top_k: 20,
    };
    const updated = { ...vectorSpace, candidate_top_k: 8 };
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([vectorSpace])),
      http.get("/api/v1/admin/tenants/tenant_test/reranker-configs", () => ok([])),
      http.patch(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/retrieval",
        async ({ request }) => {
          payload = await request.json();
          return ok(updated);
        },
      ),
    );
    renderKnowledgePage(
      ["knowledge.spaces.read", "knowledge.spaces.manage", "knowledge.query"],
      "/admin/knowledge/space_engineering/retrieval",
    );

    const topK = await screen.findByRole("spinbutton", { name: "候选 Top K" });
    await user.clear(topK);
    await user.type(topK, "8");
    await user.click(screen.getByRole("button", { name: "保存检索参数" }));

    await waitFor(() =>
      expect(payload).toEqual({
        embedding_config_id: embedding.id,
        candidate_top_k: 8,
        min_vector_score: null,
        rerank_enabled: false,
        reranker_config_id: null,
        rerank_top_n: 10,
        min_rerank_score: null,
      }),
    );
    expect(await screen.findByText("8", { exact: true })).toBeInTheDocument();
    expect(await screen.findByText("检索参数已保存")).toBeInTheDocument();
  });
});
