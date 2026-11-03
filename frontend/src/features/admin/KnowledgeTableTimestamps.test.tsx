import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import userEvent from "@testing-library/user-event";

import { KnowledgeDocumentsTable } from "@/features/admin/KnowledgeDocumentsTable";
import { KnowledgePage } from "@/features/admin/KnowledgePage";
import type { KnowledgeDocument, KnowledgeSpace } from "@/shared/api/types";
import { AuthContext, type AuthContextValue } from "@/shared/auth/AuthContext";
import { formatDateTime } from "@/shared/time";
import { server } from "@/test/server";

const space: KnowledgeSpace = {
  id: "space_engineering",
  tenant_id: "tenant_test",
  slug: "engineering",
  name: "Engineering",
  classification: "standard",
  status: "active",
  chunk_separator: "\\n\\n",
  chunk_size_chars: 4000,
  chunk_overlap_chars: 200,
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
  access_revision: 1,
  created_at: "2026-07-14T01:00:00Z",
  updated_at: "2026-07-15T02:30:00Z",
};

const document: KnowledgeDocument = {
  id: "document_release",
  tenant_id: "tenant_test",
  space_id: space.id,
  title: "Release process",
  source_uri: null,
  status: "active",
  current_version: 1,
  chunk_count: 3,
  changed_by_display_name: "Operator",
  changed_by_user: { id: "user_operator", display_name: "Operator", avatar_present: false },
  created_at: "2026-07-14T01:00:00Z",
  updated_at: "2026-07-15T02:30:00Z",
};

const auth: AuthContextValue = {
  session: {
    principal: {
      tenant_id: "tenant_test",
      subject_type: "user",
      subject_id: "user_test",
      username: "admin",
      display_name: "Administrator",
      avatar_present: false,
      permissions: ["knowledge.spaces.read"],
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
  hasPermission: (permission) => permission === "knowledge.spaces.read",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("knowledge table timestamps", () => {
  it("shows the knowledge space creation time", async () => {
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: [space],
          request_id: "req_test",
        }),
      ),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <AuthContext.Provider value={auth}>
            <KnowledgePage />
          </AuthContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("columnheader", { name: "创建时间" })).toBeInTheDocument();
    expect(await screen.findByText(formatDateTime(space.created_at))).toBeInTheDocument();
  });

  it("shows the document update time immediately after its chunk count", () => {
    render(
      <KnowledgeDocumentsTable
        archivingDocumentId={null}
        canManage={false}
        documents={[document]}
        downloadingDocumentId={null}
        loading={false}
        pendingStagingSourceId={null}
        tenantId="tenant_test"
        onArchive={vi.fn()}
        onCleanupStagingSource={vi.fn()}
        onDownload={vi.fn()}
        onReplace={vi.fn()}
        onRetryStagingConfirmation={vi.fn()}
        onView={vi.fn()}
      />,
    );

    const headers = screen.getAllByRole("columnheader").map((item) => item.textContent);
    expect(headers.indexOf("更新时间")).toBe(headers.indexOf("分块") + 1);
    expect(screen.getByText(formatDateTime(document.updated_at))).toBeInTheDocument();
  });

  it("shows the full document title in a hover tooltip", async () => {
    const user = userEvent.setup();
    const title = "Release process handbook with a title that must remain readable";

    render(
      <KnowledgeDocumentsTable
        archivingDocumentId={null}
        canManage={false}
        documents={[{ ...document, title }]}
        downloadingDocumentId={null}
        loading={false}
        pendingStagingSourceId={null}
        tenantId="tenant_test"
        onArchive={vi.fn()}
        onCleanupStagingSource={vi.fn()}
        onDownload={vi.fn()}
        onReplace={vi.fn()}
        onRetryStagingConfirmation={vi.fn()}
        onView={vi.fn()}
      />,
    );

    await user.hover(screen.getByText(title));

    expect(await screen.findByRole("tooltip")).toHaveTextContent(title);
  });
});
