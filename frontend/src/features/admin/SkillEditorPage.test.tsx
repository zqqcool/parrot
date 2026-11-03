import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("@/shared/ui/monaco", () => ({}));
vi.mock("@monaco-editor/react", () => ({ default: () => <div /> }));

import { SkillEditorPage } from "@/features/admin/SkillEditorPage";
import { AuthContext, type AuthContextValue } from "@/shared/auth/AuthContext";
import { server } from "@/test/server";

const authValue: AuthContextValue = {
  session: {
    principal: {
      tenant_id: "tenant_test",
      subject_type: "user",
      subject_id: "user_test",
      username: "admin",
      display_name: "Administrator",
      avatar_present: false,
      permissions: ["skills.read", "skills.manage"],
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
  hasPermission: (permission) => ["skills.read", "skills.manage"].includes(permission),
};

function renderSkillEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/admin/skills/skill_test/edit"]}>
        <AuthContext.Provider value={authValue}>
          <Routes>
            <Route path="/admin/skills/:skillId" element={<p>Skill detail</p>} />
            <Route path="/admin/skills/:skillId/edit" element={<SkillEditorPage />} />
          </Routes>
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

describe("SkillEditorPage", () => {
  it("renders the complete Skill editor breadcrumb hierarchy", async () => {
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/skills", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: [
            {
              id: "skill_test",
              tenant_id: "tenant_test",
              name: "北京转上海测试",
              description: "Test promotion Skill",
              instructions: "Test instructions",
              manifest: {},
              status: "draft",
              version: 1,
              current_version_id: null,
              draft_version_id: "version_draft",
              has_draft: true,
            },
          ],
          request_id: "req_skills",
        }),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/skills/skill_test/versions", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: [
            {
              id: "version_draft",
              tenant_id: "tenant_test",
              skill_id: "skill_test",
              version: 1,
              status: "draft",
              description: "Test promotion Skill",
              manifest: {},
              instructions: "Test instructions",
              package_filename: "test.zip",
              package_size_bytes: 128,
              package_sha256: "a".repeat(64),
              source_version_id: null,
              created_by_user: null,
              published_by_user: null,
              published_at: null,
              created_at: "2026-07-16T00:00:00Z",
              updated_at: "2026-07-16T00:00:00Z",
            },
          ],
          request_id: "req_versions",
        }),
      ),
      http.get(
        "/api/v1/admin/tenants/tenant_test/skills/skill_test/versions/version_draft/files",
        () =>
          HttpResponse.json({ code: "OK", message: "success", data: [], request_id: "req_files" }),
      ),
    );
    renderSkillEditor();

    expect(await screen.findByRole("heading", { name: "北京转上海测试 · 文件编辑" })).toBeVisible();
    expect(screen.getByRole("link", { name: "工作台" })).toHaveAttribute("href", "/admin");
    expect(screen.getByRole("link", { name: "Skill 管理" })).toHaveAttribute(
      "href",
      "/admin/skills",
    );
    expect(screen.getByRole("link", { name: "北京转上海测试" })).toHaveAttribute(
      "href",
      "/admin/skills/skill_test",
    );
    expect(screen.getByText("文件编辑", { selector: ".ant-breadcrumb-link" })).toBeVisible();
  });

  it("publishes an executable draft directly without requesting a build", async () => {
    const user = userEvent.setup();
    let publishRequests = 0;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/skills", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: [
            {
              id: "skill_test",
              tenant_id: "tenant_test",
              name: "北京转上海测试",
              description: "Test promotion Skill",
              instructions: "Test instructions",
              manifest: { runtime: { entrypoint: "main.py" } },
              status: "draft",
              version: 1,
              current_version_id: null,
              draft_version_id: "version_draft",
              has_draft: true,
            },
          ],
          request_id: "req_skills",
        }),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/skills/skill_test/versions", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: [
            {
              id: "version_draft",
              tenant_id: "tenant_test",
              skill_id: "skill_test",
              version: 1,
              status: "draft",
              description: "Test promotion Skill",
              manifest: { runtime: { entrypoint: "main.py" } },
              instructions: "Test instructions",
              package_filename: "test.zip",
              package_size_bytes: 128,
              package_sha256: "a".repeat(64),
              source_version_id: null,
              created_by_user: null,
              published_by_user: null,
              published_at: null,
              created_at: "2026-07-16T00:00:00Z",
              updated_at: "2026-07-16T00:00:00Z",
            },
          ],
          request_id: "req_versions",
        }),
      ),
      http.get(
        "/api/v1/admin/tenants/tenant_test/skills/skill_test/versions/version_draft/files",
        () =>
          HttpResponse.json({ code: "OK", message: "success", data: [], request_id: "req_files" }),
      ),
      http.post("/api/v1/admin/tenants/tenant_test/skills/skill_test:publish", () => {
        publishRequests += 1;
        return HttpResponse.json({
          code: "OK",
          message: "success",
          data: null,
          request_id: "req_publish",
        });
      }),
    );
    renderSkillEditor();

    expect(screen.queryByRole("button", { name: "构建草稿" })).not.toBeInTheDocument();
    const publishButton = await screen.findByRole("button", { name: "发布草稿" });
    expect(publishButton).toBeEnabled();
    await user.click(publishButton);

    await waitFor(() => expect(publishRequests).toBe(1));
  });
});
