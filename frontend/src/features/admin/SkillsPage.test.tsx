import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { SkillsPage } from "@/features/admin/SkillsPage";
import { filterSkills } from "@/features/admin/skillFilters";
import { adminApi } from "@/shared/api/client";
import { AuthContext, type AuthContextValue } from "@/shared/auth/AuthContext";
import { server } from "@/test/server";

const skills = [
  {
    id: "skill_web_search",
    tenant_id: "tenant_test",
    name: "Web Search",
    description: "Search published sources",
    instructions: "Search before answering",
    manifest: { source: "web" },
    status: "published",
    version: 3,
    bound_agents: [
      {
        id: "agent_roadmap",
        name: "Roadmap Assistant",
      },
    ],
  },
  {
    id: "skill_lark",
    tenant_id: "tenant_test",
    name: "Lark Operator",
    description: "Operate Lark Project safely",
    instructions: "Confirm before mutation",
    manifest: {},
    status: "draft",
    version: 2,
  },
  {
    id: "skill_legacy",
    tenant_id: "tenant_test",
    name: "Legacy Tool",
    description: "Deprecated integration",
    instructions: "Do not use",
    manifest: {},
    status: "disabled",
    version: 1,
    bound_agents: null,
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
      permissions: ["skills.read", "skills.manage", "agents.read", "agents.manage"],
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
  hasPermission: (permission) =>
    ["skills.read", "skills.manage", "agents.read", "agents.manage"].includes(permission),
};

function renderSkillsPage(auth: AuthContextValue = authValue) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AuthContext.Provider value={auth}>
          <SkillsPage />
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SkillsPage", () => {
  it("filters server results by status", () => {
    expect(filterSkills(skills, "all").map((skill) => skill.id)).toEqual([
      "skill_web_search",
      "skill_lark",
      "skill_legacy",
    ]);
    expect(filterSkills(skills, "draft").map((skill) => skill.id)).toEqual(["skill_lark"]);
  });

  it("renders server search results and keeps status filtering local", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/skills", ({ request }) => {
        const query = new URL(request.url).searchParams.get("query");
        const data = query === "lark" ? [skills[1]] : skills;
        return HttpResponse.json({ code: "OK", message: "success", data, request_id: "req_list" });
      }),
    );
    renderSkillsPage();

    expect(await screen.findByRole("article", { name: "Skill Web Search" })).toBeInTheDocument();
    expect(screen.getByText("总 Skill").nextElementSibling).toHaveTextContent("3");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const webSearchCard = screen.getByRole("article", { name: "Skill Web Search" });
    expect(within(webSearchCard).getByLabelText("关联 Agent")).toHaveClass(
      "skill-card-bound-agents--active",
    );
    expect(
      within(webSearchCard).getByRole("link", { name: "查看关联 Agent Roadmap Assistant" }),
    ).toHaveAttribute("href", "/admin/agents/agent_roadmap");
    expect(within(webSearchCard).queryByText("Skill ID")).not.toBeInTheDocument();
    expect(screen.getByText("无查看关联 Agent 的权限")).toBeVisible();

    await user.type(screen.getByRole("textbox", { name: "按名称或描述搜索" }), "lark");
    expect(await screen.findByRole("article", { name: "Skill Lark Operator" })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("article", { name: "Skill Web Search" })).not.toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: /重\s*置/ }));
    expect(await screen.findByRole("article", { name: "Skill Web Search" })).toBeInTheDocument();
  });

  it("opens the version route and preserves the guarded publish operation", async () => {
    const user = userEvent.setup();
    let published = false;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/skills", () =>
        HttpResponse.json({ code: "OK", message: "success", data: skills, request_id: "req_list" }),
      ),
      http.post(
        "/api/v1/admin/tenants/tenant_test/skills/skill_lark:publish",
        async ({ request }) => {
          published = (await request.json()) !== undefined;
          return HttpResponse.json({
            code: "OK",
            message: "success",
            data: { ...skills[1], status: "published" },
            request_id: "req_publish",
          });
        },
      ),
    );
    renderSkillsPage();

    const larkCard = await screen.findByRole("article", { name: "Skill Lark Operator" });
    await user.click(within(larkCard).getByRole("button", { name: /查看版本/ }));

    await user.click(within(larkCard).getByRole("button", { name: /发\s*布/ }));
    await user.click(await screen.findByRole("button", { name: "确认发布" }));
    await waitFor(() => expect(published).toBe(true));
  });

  it("imports a ZIP package instead of collecting inline instructions", async () => {
    const user = userEvent.setup();
    let importedFilename = "";
    vi.spyOn(adminApi, "importSkill").mockImplementation((_tenantId, file) => {
      importedFilename = file.name;
      return Promise.resolve(skills[1] as never);
    });
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/skills", () =>
        HttpResponse.json({ code: "OK", message: "success", data: [], request_id: "req_list" }),
      ),
    );
    renderSkillsPage();

    await user.click(await screen.findByRole("button", { name: "导入 Skill" }));
    expect(screen.getByRole("dialog", { name: "导入 Skill" })).toHaveTextContent("SKILL.md");
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("Skill import file input is missing");
    await user.upload(input, new File(["archive"], "lark.zip"));
    await screen.findByText("lark.zip");
    const submit = screen.getByRole("button", { name: "OK" });
    expect(submit).toBeEnabled();
    await user.click(submit);

    await waitFor(() => expect(importedFilename).toBe("lark.zip"));
  });

  it("tests bound Skill recall through the Agent runtime ranking contract", async () => {
    const user = userEvent.setup();
    let requestBody: unknown;
    let agentUpdateBody: unknown;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/skills", () =>
        HttpResponse.json({ code: "OK", message: "success", data: skills, request_id: "req_list" }),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/agents", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: [
            {
              id: "agent_roadmap",
              tenant_id: "tenant_test",
              runtime_agent_id: "roadmap",
              slug: "roadmap",
              name: "Roadmap Assistant",
              description: "",
              system_prompt: "",
              capability_relevance_threshold: 0.4,
              status: "active",
              agent_type_key: "functional",
              published: true,
              allow_anonymous: false,
              avatar_present: false,
            },
          ],
          request_id: "req_agents",
        }),
      ),
      http.post(
        "/api/v1/admin/tenants/tenant_test/agents/agent_roadmap/skills:search",
        async ({ request }) => {
          requestBody = await request.json();
          return HttpResponse.json({
            code: "OK",
            message: "success",
            data: {
              agent_id: "agent_roadmap",
              agent_type_key: "functional",
              query: "我想登记入住",
              retrieval_method: "hybrid",
              eligible_skill_count: 3,
              configured_relevance_threshold: 0.4,
              applied_relevance_threshold: 0.55,
              candidates: [
                {
                  id: "skill_web_search",
                  name: "Web Search",
                  description: "Search published sources",
                  version: 3,
                  rank: 1,
                  relevance_score: 0.72,
                },
              ],
            },
            request_id: "req_recall",
          });
        },
      ),
      http.patch("/api/v1/admin/tenants/tenant_test/agents/agent_roadmap", async ({ request }) => {
        agentUpdateBody = await request.json();
        return HttpResponse.json({
          code: "OK",
          message: "success",
          data: {
            id: "agent_roadmap",
            tenant_id: "tenant_test",
            runtime_agent_id: "roadmap",
            slug: "roadmap",
            name: "Roadmap Assistant",
            description: "",
            system_prompt: "",
            capability_relevance_threshold: 0.55,
            status: "active",
            agent_type_key: "functional",
            published: true,
            allow_anonymous: false,
            avatar_present: false,
          },
          request_id: "req_agent_update",
        });
      }),
    );
    renderSkillsPage();

    const recallButton = await screen.findByRole("button", { name: "召回验证" });
    expect(recallButton).toHaveClass("ant-btn-color-primary", "ant-btn-variant-outlined");
    await user.click(recallButton);
    const dialog = screen.getByRole("dialog", { name: "Skill 召回验证" });
    const agentSelect = within(dialog).getByRole("combobox", {
      name: "选择用于 Skill 召回验证的 Agent",
    });
    await user.click(agentSelect);
    await user.click(
      await screen.findByText("Roadmap Assistant", {
        selector: ".ant-select-item-option-content",
      }),
    );
    const thresholdInput = within(dialog).getByRole("spinbutton", {
      name: "设置 Agent 能力召回最低相关度",
    });
    expect(thresholdInput).toHaveValue("0.40");
    await user.clear(thresholdInput);
    await user.type(thresholdInput, "0.55");
    const queryInput = within(dialog).getByRole("textbox", {
      name: "输入用于 Skill 召回验证的用户问题",
    });
    expect(queryInput).toHaveAttribute("maxLength", "500");
    await user.type(queryInput, "我想登记入住");
    expect(queryInput).toHaveValue("我想登记入住");
    const submitRecall = within(dialog).getByRole("button", { name: "开始召回" });
    expect(submitRecall).toBeEnabled();
    await user.click(submitRecall);

    await waitFor(() =>
      expect(requestBody).toEqual({ query: "我想登记入住", relevance_threshold: 0.55 }),
    );
    expect(await within(dialog).findByText("召回方式：BM25 + 向量融合")).toBeVisible();
    expect(within(dialog).getByRole("link", { name: "Web Search" })).toHaveAttribute(
      "href",
      "/admin/skills/skill_web_search",
    );
    expect(within(dialog).getByText("第 1 位")).toBeVisible();
    expect(within(dialog).getByText("相关度 0.720")).toBeVisible();

    await user.click(within(dialog).getByRole("button", { name: "应用到 Agent" }));
    await waitFor(() => expect(agentUpdateBody).toEqual({ capability_relevance_threshold: 0.55 }));
    expect(within(dialog).getByText("已应用到 Agent 后续召回")).toBeVisible();
  });

  it("hides recall validation when Agent configuration is not visible", async () => {
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/skills", () =>
        HttpResponse.json({ code: "OK", message: "success", data: [], request_id: "req_list" }),
      ),
    );
    renderSkillsPage({
      ...authValue,
      hasPermission: (permission) => permission !== "agents.read",
    });

    expect(await screen.findByRole("button", { name: "导入 Skill" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "召回验证" })).not.toBeInTheDocument();
  });
});
