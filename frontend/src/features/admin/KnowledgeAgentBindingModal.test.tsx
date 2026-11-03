import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KnowledgeAgentBindingModal } from "@/features/admin/KnowledgeAgentBindingModal";
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

const agent = {
  id: "agent_knowledge",
  tenant_id: "tenant_test",
  agent_type_key: "knowledge",
  allow_anonymous: false,
  avatar_present: false,
  description: "Searches the engineering knowledge base.",
  name: "Engineering knowledge assistant",
  published: true,
  runtime_agent_id: "runtime_knowledge",
  slug: "engineering-knowledge",
  status: "active",
  system_prompt: "",
};

const ok = (data: unknown) =>
  HttpResponse.json({ code: "OK", message: "success", data, request_id: "req_test" });

function renderModal() {
  server.use(
    http.get("/api/v1/admin/agent-types", () =>
      ok([
        {
          key: "knowledge",
          name: "知识型",
          description: "使用知识库回答问题。",
          is_default: true,
          uses_knowledge: true,
          restricts_executable_skills: true,
        },
      ]),
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <KnowledgeAgentBindingModal
        open
        space={space}
        tenantId="tenant_test"
        onChanged={vi.fn()}
        onClose={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

afterEach(() => cleanup());

describe("KnowledgeAgentBindingModal", () => {
  it("offers only published active knowledge Agents", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/agents", () =>
        ok([
          agent,
          {
            ...agent,
            id: "agent_draft",
            name: "Draft knowledge assistant",
            slug: "draft-knowledge",
            published: false,
          },
        ]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/agents", () =>
        ok({ agent_ids: [] }),
      ),
    );
    renderModal();

    const dialog = await screen.findByRole("dialog", { name: "关联 Agent · Engineering" });
    await user.click(within(dialog).getByRole("combobox", { name: "目标 Agent" }));

    expect(
      await screen.findByRole("option", {
        name: "Engineering knowledge assistant（engineering-knowledge）",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "Draft knowledge assistant（draft-knowledge）" }),
    ).not.toBeInTheDocument();
    expect(dialog).toHaveTextContent("已有的停用或未发布 Agent 仍会显示，并可解除关联");
  });

  it("shows a disabled bound Agent and allows removing its binding", async () => {
    const user = userEvent.setup();
    let removed = false;
    const disabledAgent = {
      ...agent,
      id: "agent_disabled",
      name: "Disabled knowledge assistant",
      slug: "disabled-knowledge",
      status: "disabled",
    };
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/agents", () => ok([agent, disabledAgent])),
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_engineering/agents", () =>
        ok({ agent_ids: [disabledAgent.id] }),
      ),
      http.delete(
        "/api/v1/admin/tenants/tenant_test/agents/agent_disabled/knowledge-spaces/space_engineering",
        () => {
          removed = true;
          return ok({ space_ids: [] });
        },
      ),
    );
    renderModal();

    const dialog = await screen.findByRole("dialog", { name: "关联 Agent · Engineering" });
    const name = await within(dialog).findByText("Disabled knowledge assistant");
    const row = name.closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("已停用")).toBeInTheDocument();

    await user.click(within(row as HTMLElement).getByRole("button", { name: "解除关联" }));
    const confirmation = await screen.findByText("解除与 Disabled knowledge assistant 的关联？");
    const popover = confirmation.closest(".ant-popover");
    expect(popover).not.toBeNull();
    await user.click(within(popover as HTMLElement).getByRole("button", { name: "解除关联" }));

    await waitFor(() => expect(removed).toBe(true));
    await waitFor(() =>
      expect(within(dialog).queryByText("Disabled knowledge assistant")).not.toBeInTheDocument(),
    );
  });
});
