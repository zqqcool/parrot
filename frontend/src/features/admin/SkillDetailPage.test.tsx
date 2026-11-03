import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { SkillDetailPage } from "@/features/admin/SkillDetailPage";
import { AuthContext, type AuthContextValue } from "@/shared/auth/AuthContext";
import { server } from "@/test/server";

const skill = {
  id: "skill_web_search",
  tenant_id: "tenant_test",
  name: "Web Search",
  description: "Search published sources",
  instructions: "Search before answering",
  manifest: { source: "web" },
  status: "published",
  version: 3,
  current_version_id: "skill_version_3",
};

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

function renderSkillDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/admin/skills/skill_web_search"]}>
        <AuthContext.Provider value={authValue}>
          <Routes>
            <Route path="/admin/skills" element={<p>Skills list</p>} />
            <Route path="/admin/skills/:skillId" element={<SkillDetailPage />} />
          </Routes>
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SkillDetailPage", () => {
  it("renders the complete Skill detail breadcrumb hierarchy", async () => {
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/skills", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: [skill],
          request_id: "req_list",
        }),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/skills/skill_web_search/versions", () =>
        HttpResponse.json({ code: "OK", message: "success", data: [], request_id: "req_versions" }),
      ),
    );
    renderSkillDetail();

    expect(await screen.findByRole("heading", { name: "Web Search" })).toBeVisible();
    expect(screen.getByRole("link", { name: "工作台" })).toHaveAttribute("href", "/admin");
    expect(screen.getByRole("link", { name: "Skill 管理" })).toHaveAttribute(
      "href",
      "/admin/skills",
    );
    expect(screen.getByText("Web Search", { selector: ".ant-breadcrumb-link" })).toBeVisible();
  });

  it("deletes an unbound Skill after confirmation", async () => {
    const user = userEvent.setup();
    let deleted = false;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/skills", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: [skill],
          request_id: "req_list",
        }),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/skills/skill_web_search/versions", () =>
        HttpResponse.json({ code: "OK", message: "success", data: [], request_id: "req_versions" }),
      ),
      http.delete("/api/v1/admin/tenants/tenant_test/skills/skill_web_search", () => {
        deleted = true;
        return HttpResponse.json({
          code: "OK",
          message: "success",
          data: { deleted: true },
          request_id: "req_delete",
        });
      }),
    );
    renderSkillDetail();

    await user.click(await screen.findByRole("button", { name: "删除 Skill" }));
    await user.click(await screen.findByRole("button", { name: "确认删除" }));

    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Skills list")).toBeInTheDocument();
  });
});
