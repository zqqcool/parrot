import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentKnowledgeSection } from "@/features/admin/AgentKnowledgeSection";
import { server } from "@/test/server";

const agent = {
  id: "agent_test",
  tenant_id: "tenant_test",
  runtime_agent_id: "runtime_test",
  slug: "knowledge-agent",
  name: "Knowledge Agent",
  description: "",
  system_prompt: "Answer from evidence.",
  capability_relevance_threshold: 0.4,
  status: "active",
  agent_type_key: "knowledge",
  published: true,
  allow_anonymous: false,
  avatar_present: false,
};

const ok = (data: unknown) =>
  HttpResponse.json({ code: "OK", message: "success", data, request_id: "req_test" });

function renderSection(
  canRead: boolean,
  canManage: boolean,
  canQuery = false,
  usesKnowledge = true,
  selectedAgent = agent,
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onSaved = vi.fn();
  const view = render(
    <QueryClientProvider client={client}>
      <AgentKnowledgeSection
        agent={selectedAgent}
        canManage={canManage}
        canQuery={canQuery}
        canRead={canRead}
        onSaved={onSaved}
        tenantId="tenant_test"
        usesKnowledge={usesKnowledge}
      />
    </QueryClientProvider>,
  );
  return { ...view, onSaved };
}

afterEach(() => cleanup());

describe("AgentKnowledgeSection", () => {
  it("shows a no-permission state without knowledge-space visibility", () => {
    renderSection(false, false);

    expect(screen.getByText("当前账号没有查看可绑定知识空间的权限。")).toBeInTheDocument();
  });

  it("shows an empty, read-only binding list", async () => {
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([])),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/knowledge-spaces", () =>
        ok({ space_ids: [] }),
      ),
    );
    renderSection(true, false);

    expect(await screen.findByText("当前 Agent 尚未绑定知识库")).toBeInTheDocument();
    expect(screen.getByText("当前账号只能查看知识库绑定，没有修改权限。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存知识库绑定" })).not.toBeInTheDocument();
  });

  it("paginates bound knowledge spaces with the shared 10-row default", async () => {
    const user = userEvent.setup();
    const spaces = Array.from({ length: 11 }, (_, index) => ({
      id: `space_${index + 1}`,
      name: `Space ${index + 1}`,
      slug: `space-${index + 1}`,
      classification: "standard",
      status: "active",
    }));
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok(spaces)),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/knowledge-spaces", () =>
        ok({ space_ids: spaces.map((space) => space.id) }),
      ),
    );
    const { container } = renderSection(true, false);

    expect(await screen.findByText("Space 1")).toBeInTheDocument();
    expect(screen.queryByText("Space 11")).not.toBeInTheDocument();
    const secondPage = container.querySelector<HTMLElement>('.ant-pagination-item[title="2"]');
    if (!secondPage) throw new Error("Second knowledge-binding page is missing");
    await user.click(secondPage);

    expect(await screen.findByText("Space 11")).toBeInTheDocument();
    expect(screen.queryByText("Space 1")).not.toBeInTheDocument();
  });

  it("disables real retrieval tests for Agent types that do not use knowledge", () => {
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([])),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/knowledge-spaces", () =>
        ok({ space_ids: [] }),
      ),
    );
    renderSection(true, false, true, false);

    expect(screen.getByRole("button", { name: "真实检索测试" })).toBeDisabled();
    expect(screen.getByTitle("当前 Agent 类型不会读取知识库")).toBeInTheDocument();
  });

  it("disables binding changes when current bindings are hidden", async () => {
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([])),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/knowledge-spaces", () =>
        HttpResponse.json(
          { code: "RESOURCE_NOT_FOUND", message: "not found", request_id: "req_test" },
          { status: 404 },
        ),
      ),
    );
    renderSection(true, true);

    expect(
      await screen.findByText("当前账号没有查看该 Agent 全部知识库绑定的权限，已禁用绑定操作。"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存知识库绑定" })).not.toBeInTheDocument();
  });

  it("binds and unbinds knowledge spaces from row actions", async () => {
    const user = userEvent.setup();
    const updates: string[] = [];
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () =>
        ok([
          {
            id: "space_bound",
            name: "Bound space",
            slug: "bound",
            classification: "standard",
            status: "active",
          },
          {
            id: "space_free",
            name: "Free space",
            slug: "free",
            classification: "standard",
            status: "active",
          },
        ]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/knowledge-spaces", () =>
        ok({ space_ids: ["space_bound"] }),
      ),
      http.post(
        "/api/v1/admin/tenants/tenant_test/agents/agent_test/knowledge-spaces/space_free",
        () => {
          updates.push("bind:space_free");
          return ok({ space_ids: ["space_bound", "space_free"] });
        },
      ),
      http.delete(
        "/api/v1/admin/tenants/tenant_test/agents/agent_test/knowledge-spaces/space_bound",
        () => {
          updates.push("unbind:space_bound");
          return ok({ space_ids: ["space_free"] });
        },
      ),
    );
    renderSection(true, true);

    expect(
      screen.queryByText(/知识空间的用户和用户组授权仅控制管理台访问/),
    ).not.toBeInTheDocument();
    expect(await screen.findByText("Bound space")).toBeInTheDocument();
    expect(screen.queryByText("Free space")).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "搜索并选择要绑定的知识库" }));
    await user.click(await screen.findByText("Free space（标准 · free）"));
    await user.click(screen.getByRole("button", { name: "添加绑定" }));
    await waitFor(() => expect(updates).toEqual(["bind:space_free"]));
    const freeRow = (await screen.findByText("Free space")).closest("tr");
    if (!(freeRow instanceof HTMLTableRowElement)) throw new Error("Expected free-space row");
    expect(within(freeRow).getByRole("button", { name: "取消绑定" })).toBeInTheDocument();

    const boundRow = screen.getByText("Bound space").closest("tr");
    if (!(boundRow instanceof HTMLTableRowElement)) throw new Error("Expected bound-space row");
    await user.click(within(boundRow).getByRole("button", { name: "取消绑定" }));
    await user.click(await screen.findByRole("button", { name: "确认取消" }));
    await waitFor(() => expect(updates).toEqual(["bind:space_free", "unbind:space_bound"]));
  });

  it("confirms before an anonymous Agent exposes another knowledge space", async () => {
    const user = userEvent.setup();
    let bound = false;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () =>
        ok([
          {
            id: "space_public",
            name: "Public runbook",
            slug: "public-runbook",
            classification: "standard",
            status: "active",
          },
        ]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/knowledge-spaces", () =>
        ok({ space_ids: [] }),
      ),
      http.post(
        "/api/v1/admin/tenants/tenant_test/agents/agent_test/knowledge-spaces/space_public",
        () => {
          bound = true;
          return ok({ space_ids: ["space_public"] });
        },
      ),
    );
    renderSection(true, true, false, true, { ...agent, allow_anonymous: true });

    await user.click(await screen.findByRole("combobox", { name: "搜索并选择要绑定的知识库" }));
    await user.click(await screen.findByText("Public runbook（标准 · public-runbook）"));
    await user.click(screen.getByRole("button", { name: "添加绑定" }));
    expect(bound).toBe(false);
    await user.click(await screen.findByRole("button", { name: "确认绑定" }));

    await waitFor(() => expect(bound).toBe(true));
  });

  it("runs the real Agent knowledge_search test and displays its retrieval provenance", async () => {
    const user = userEvent.setup();
    let payload: unknown;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () => ok([])),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/knowledge-spaces", () =>
        ok({ space_ids: [] }),
      ),
      http.post(
        "/api/v1/admin/tenants/tenant_test/agents/agent_test/knowledge-search-test",
        async ({ request }) => {
          payload = await request.json();
          return ok({
            status: "degraded",
            retrieval_method: "hybrid_partial",
            candidate_count: 3,
            duration_ms: 12,
            degradation_reasons: ["embedding_or_vector_service_unavailable"],
            items: [
              {
                citation_id: "chunk_1",
                title: "Release runbook",
                citation_anchor: "chunk-1",
                space_id: "space_engineering",
                retrieval_method: "lexical_fallback",
                score: 0.031,
                excerpt: "Deploy safely.",
                embedding_config_name: "Engineering embedding · model-a",
                reranker_config_name: null,
                degradation_reason: "embedding_or_vector_service_unavailable",
                slide_no: null,
                media_refs: [],
              },
            ],
          });
        },
      ),
    );
    renderSection(true, false, true);

    expect(screen.queryByText("返回条数")).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "真实检索测试" }));
    const dialog = await screen.findByRole("dialog", { name: "真实工具检索测试" });
    expect(within(dialog).getByText("返回条数")).toBeInTheDocument();
    expect(within(dialog).getByRole("spinbutton", { name: "返回条数" })).toHaveDisplayValue("6");
    await user.type(within(dialog).getByLabelText("检索问题"), "如何发布？");
    await user.click(within(dialog).getByRole("button", { name: "开始真实检索" }));

    await waitFor(() => expect(payload).toEqual({ query: "如何发布？", limit: 6 }));
    expect(await within(dialog).findByText("Release runbook")).toBeInTheDocument();
    expect(within(dialog).getByText("Engineering embedding · model-a")).toBeInTheDocument();
    expect(within(dialog).getByText("embedding_or_vector_service_unavailable")).toBeInTheDocument();
  });
});
