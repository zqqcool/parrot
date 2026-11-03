import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App as AntdApp } from "antd";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { KnowledgeDocumentDetailPage } from "@/features/admin/KnowledgeDocumentDetailPage";
import { KnowledgeDocumentsPage } from "@/features/admin/KnowledgeDocumentsPage";
import { KnowledgePage } from "@/features/admin/KnowledgePage";
import { KnowledgeRetrievalPage } from "@/features/admin/KnowledgeRetrievalPage";
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
  text_processing: { normalize_whitespace: false, remove_urls_and_emails: false },
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

const document = {
  id: "document_release",
  tenant_id: "tenant_test",
  space_id: space.id,
  title: "Release process",
  source_uri: "https://docs.example.test/release",
  status: "active",
  current_version: 1,
  chunk_count: 3,
  changed_by_display_name: "Operator",
  changed_by_user: { id: "user_operator", display_name: "Operator", avatar_present: false },
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

function renderKnowledgeFlow(
  permissions = [
    "knowledge.spaces.read",
    "knowledge.spaces.manage",
    "knowledge.documents.read",
    "knowledge.documents.manage",
  ],
  initialEntry = "/admin/knowledge/space_engineering/documents",
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
              <Route
                path="/admin/knowledge/:spaceId/documents"
                element={<KnowledgeDocumentsPage />}
              />
              <Route
                path="/admin/knowledge/:spaceId/documents/:documentId"
                element={<KnowledgeDocumentDetailPage />}
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

beforeEach(() => {
  server.use(
    http.get(
      "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/ingestions",
      () => ok([]),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/sources", () =>
      ok({ items: [], page: 1, page_size: 10, total: 0 }),
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("KnowledgeDocumentsPage", () => {
  it("shows a staging upload in the document table before a document exists", async () => {
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([space])),
      http.get(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/documents",
        () => ok([]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/sources", () =>
        ok({
          items: [
            {
              id: "source_staging",
              title: "Customer handbook",
              original_filename: "customer-handbook.pdf",
              content_type: "application/pdf",
              size_bytes: 2048,
              change_kind: "create",
              status: "staging",
              document_id: null,
              attempts: 0,
              error_code: null,
              created_by_display_name: "Administrator",
              created_by_user: {
                id: "user_test",
                display_name: "Administrator",
                avatar_present: false,
              },
              created_at: "2026-07-22T15:20:19Z",
              updated_at: "2026-07-22T15:20:19Z",
            },
          ],
          page: 1,
          page_size: 10,
          total: 1,
        }),
      ),
    );

    renderKnowledgeFlow();

    expect(await screen.findByText("customer-handbook.pdf")).toBeInTheDocument();
    expect(screen.getByText("待确认")).toBeInTheDocument();
    expect(screen.getByText("尚未完成上传确认")).toBeInTheDocument();
    expect(screen.getAllByRole("table")).toHaveLength(1);
  });

  it("keeps a pending replacement on its existing document row", async () => {
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([space])),
      http.get(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/documents",
        () => ok([document]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/sources", () =>
        ok({
          items: [
            {
              id: "source_replacement",
              title: document.title,
              original_filename: "release-v2.pdf",
              content_type: "application/pdf",
              size_bytes: 2048,
              change_kind: "replace",
              status: "staging",
              document_id: document.id,
              attempts: 0,
              error_code: null,
              created_by_display_name: "Administrator",
              created_by_user: {
                id: "user_test",
                display_name: "Administrator",
                avatar_present: false,
              },
              created_at: "2026-07-22T15:20:19Z",
              updated_at: "2026-07-22T15:20:19Z",
            },
          ],
          page: 1,
          page_size: 100,
          total: 1,
        }),
      ),
    );

    renderKnowledgeFlow();

    expect(await screen.findByText(document.title)).toBeInTheDocument();
    expect(screen.getByText("待确认更新")).toBeInTheDocument();
    expect(screen.getByText("新版本尚未完成上传确认")).toBeInTheDocument();
    expect(screen.getAllByRole("table")).toHaveLength(1);
  });

  it("opens a knowledge space's documents from the knowledge list", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([space])),
      http.get(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/documents",
        ({ request }) =>
          ok(new URL(request.url).searchParams.get("query") === "missing" ? [] : [document]),
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
    renderKnowledgeFlow(undefined, "/admin/knowledge");

    expect(await screen.findByText("Engineering")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "查看文档" }));

    expect(await screen.findByRole("heading", { name: "Engineering · 文档" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "知识库" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "添加文档" }));
    const addDialog = await screen.findByRole("dialog", { name: "添加文档" });
    expect(within(addDialog).getByRole("tab", { name: "上传文件" })).toBeInTheDocument();
    expect(within(addDialog).getByRole("tab", { name: "录入文本" })).toBeInTheDocument();
    expect(screen.getByText("Release process")).toBeInTheDocument();
  });

  it("opens a document's parsed chunks from the document list", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([space])),
      http.get(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/documents",
        () => ok([document]),
      ),
      http.get(
        "/api/v1/admin/tenants/tenant_test/knowledge/documents/document_release/versions",
        () =>
          ok([
            {
              id: "version_release",
              document_id: document.id,
              source_id: null,
              version: 1,
              status: "published",
              extraction_status: "completed",
              chunk_size_chars: 4000,
              chunk_overlap_chars: 200,
              published_at: "2026-07-14T01:00:00Z",
              created_at: "2026-07-14T01:00:00Z",
            },
          ]),
      ),
      http.get(
        "/api/v1/admin/tenants/tenant_test/knowledge/documents/document_release/versions/version_release/chunks",
        () =>
          ok({
            items: [
              {
                id: "chunk_release",
                ordinal: 1,
                citation_anchor: "chunk-1",
                content: "Deploy only after approval.",
                content_chars: 26,
              },
            ],
            page: 1,
            page_size: 20,
            total: 1,
          }),
      ),
    );
    renderKnowledgeFlow();

    await user.click(await screen.findByRole("button", { name: "查看" }));

    expect(await screen.findByRole("heading", { name: "Release process" })).toBeInTheDocument();
    expect(screen.getByText("Deploy only after approval.")).toBeInTheDocument();
  });

  it("filters documents and displays scoped knowledge retrieval results", async () => {
    const user = userEvent.setup();
    let receivedQuery = "";
    const fullChunkContent = "# 发布流程\n\n发布前需要完成审批、回归测试和负责人确认。";
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([space])),
      http.get(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/documents",
        () => ok([document]),
      ),
      http.get(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/search",
        ({ request }) => {
          receivedQuery = new URL(request.url).searchParams.get("query") ?? "";
          return ok([
            {
              chunk_id: "chunk_release",
              document_id: document.id,
              document_version_id: "version_release",
              title: document.title,
              citation_anchor: "chunk-1",
              content_chars: fullChunkContent.length,
              score: 0.375,
              excerpt: "发布前需要完成审批。…",
              excerpt_truncated: true,
              retrieval_method: "hybrid",
              match_sources: ["lexical", "vector"],
              vector_score: 0.8,
              embedding_config_name: "Production embedding · text-embedding-3-large",
              reranker_config_name: null,
              degradation_reason: null,
              slide_no: null,
              media_refs: [],
            },
          ]);
        },
      ),
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/citations/chunk_release", () =>
        ok({
          citation_id: "chunk_release",
          document_id: document.id,
          document_version_id: "version_release",
          title: document.title,
          citation_anchor: "chunk-1",
          excerpt: "发布前需要完成审批。…",
          content_chars: fullChunkContent.length,
          content: fullChunkContent,
          slide_no: null,
          media_refs: [],
        }),
      ),
    );
    renderKnowledgeFlow(["knowledge.spaces.read", "knowledge.documents.read", "knowledge.query"]);

    const filter = await screen.findByRole("textbox", { name: "搜索文档标题或来源" });
    await user.type(filter, "missing");
    await waitFor(() => expect(screen.queryByText("Release process")).not.toBeInTheDocument());
    await user.clear(filter);
    expect(await screen.findByText("Release process")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "检索测试" }));
    await user.type(
      screen.getByRole("textbox", { name: "输入问题以测试知识召回" }),
      "发布前需要什么？",
    );
    await user.click(screen.getByRole("button", { name: "开始检索" }));

    await waitFor(() => expect(receivedQuery).toBe("发布前需要什么？"));
    expect(await screen.findByText("1 个召回片段")).toBeInTheDocument();
    expect(screen.getByText("融合排序分 0.375")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "查看完整片段" }));
    expect(await screen.findByText(/回归测试和负责人确认/)).toBeInTheDocument();
  });

  it("creates and archives documents in a selected knowledge space", async () => {
    const user = userEvent.setup();
    let createdPayload: unknown;
    let archivedDocumentId = "";
    let documents: (typeof document)[] = [];
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([space])),
      http.get(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/documents",
        () => ok(documents),
      ),
      http.post(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/documents",
        async ({ request }) => {
          createdPayload = await request.json();
          documents = [document];
          return ok(document);
        },
      ),
      http.post(
        "/api/v1/admin/tenants/tenant_test/knowledge/documents/document_release/archive",
        () => {
          archivedDocumentId = document.id;
          documents = [{ ...document, status: "archived" }];
          return ok(null);
        },
      ),
    );
    renderKnowledgeFlow();

    await user.click(await screen.findByRole("button", { name: "添加文档" }));
    const dialog = await screen.findByRole("dialog", { name: "添加文档" });
    await user.click(within(dialog).getByRole("tab", { name: "录入文本" }));
    await user.type(within(dialog).getByRole("textbox", { name: "标题" }), "Release process");
    await user.type(within(dialog).getByRole("textbox", { name: "内容" }), "Release instructions");
    await user.click(within(dialog).getByRole("button", { name: "创建文档" }));

    await waitFor(() =>
      expect(createdPayload).toEqual({
        title: "Release process",
        content: "Release instructions",
      }),
    );
    await user.click(await screen.findByRole("button", { name: "归档" }));
    await user.click(await screen.findByRole("button", { name: "确认归档" }));

    await waitFor(() => expect(archivedDocumentId).toBe(document.id));
    expect(await screen.findByText("已归档")).toBeInTheDocument();
  });

  it("keeps the document view read-only without document permissions", async () => {
    server.use(http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([space])));
    renderKnowledgeFlow(["knowledge.spaces.read"]);

    expect(await screen.findByText("当前账号没有查看知识文档的权限。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "添加文档" })).not.toBeInTheDocument();
  });
});
