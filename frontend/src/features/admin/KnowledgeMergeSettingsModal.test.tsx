import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App as AntdApp } from "antd";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KnowledgeMergeSettingsModal } from "@/features/admin/KnowledgeMergeSettingsModal";
import { RequestErrorNotifier } from "@/shared/ui";
import { server } from "@/test/server";

const settings = {
  tenant_id: "tenant_test",
  merge_rerank_enabled: true,
  reranker_config_id: "reranker_active",
  rerank_top_n: 20,
  result_top_k: 6,
  min_rerank_score: 0.2,
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
};

const rerankers = [
  {
    id: "reranker_active",
    tenant_id: "tenant_test",
    name: "Active reranker",
    provider: "parrot_http",
    model: "bge-reranker-v2",
    base_url: "https://models.example.test/v1",
    credential_configured: true,
    status: "active",
  },
  {
    id: "reranker_disabled",
    tenant_id: "tenant_test",
    name: "Disabled reranker",
    provider: "parrot_http",
    model: "legacy-reranker",
    base_url: "https://models.example.test/v1",
    credential_configured: true,
    status: "disabled",
  },
];

const ok = (data: unknown) =>
  HttpResponse.json({ code: "OK", message: "success", data, request_id: "req_test" });

function renderModal(onClose = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <AntdApp>
      <QueryClientProvider client={client}>
        <RequestErrorNotifier />
        <KnowledgeMergeSettingsModal open tenantId="tenant_test" onClose={onClose} />
      </QueryClientProvider>
    </AntdApp>,
  );
  return onClose;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("KnowledgeMergeSettingsModal", () => {
  it("uses server policy and lists only active rerankers", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/merge-settings", () => ok(settings)),
      http.get("/api/v1/admin/tenants/tenant_test/reranker-configs", () => ok(rerankers)),
    );
    renderModal();

    const dialog = await screen.findByRole("dialog", { name: "多库合并配置" });
    expect(await within(dialog).findByText(/至少 2 个/)).toHaveTextContent("每库最多取 12 条候选");
    expect(
      await within(dialog).findByRole("spinbutton", { name: "送入重排候选 Top N" }),
    ).toHaveValue("20");
    expect(within(dialog).getByRole("spinbutton", { name: /最终返回 Top K/ })).toHaveValue("6");

    await user.click(within(dialog).getByRole("combobox", { name: "重排序配置" }));
    expect(await screen.findAllByText(/Active reranker/)).toHaveLength(2);
    expect(screen.queryByText(/Disabled reranker/)).not.toBeInTheDocument();
  });

  it("saves the complete merge policy payload", async () => {
    const user = userEvent.setup();
    let payload: unknown;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/merge-settings", () => ok(settings)),
      http.get("/api/v1/admin/tenants/tenant_test/reranker-configs", () => ok(rerankers)),
      http.put(
        "/api/v1/admin/tenants/tenant_test/knowledge/merge-settings",
        async ({ request }) => {
          payload = await request.json();
          return ok({ ...settings, result_top_k: 4 });
        },
      ),
    );
    const onClose = renderModal();
    const dialog = await screen.findByRole("dialog", { name: "多库合并配置" });
    const resultTopK = await within(dialog).findByRole("spinbutton", { name: /最终返回 Top K/ });

    await user.clear(resultTopK);
    await user.type(resultTopK, "4");
    await user.click(within(dialog).getByRole("button", { name: /保\s*存/ }));

    await waitFor(() =>
      expect(payload).toEqual({
        merge_rerank_enabled: true,
        reranker_config_id: "reranker_active",
        rerank_top_n: 20,
        result_top_k: 4,
        min_rerank_score: 0.2,
      }),
    );
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
