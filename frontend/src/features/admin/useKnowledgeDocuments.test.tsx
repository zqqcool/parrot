import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { useKnowledgeDocuments } from "@/features/admin/useKnowledgeDocuments";
import type { KnowledgeIngestion } from "@/shared/api/types";
import { server } from "@/test/server";

const ok = (data: unknown) =>
  HttpResponse.json({ code: "OK", message: "success", data, request_id: "req_test" });

function ingestion(id: string): KnowledgeIngestion {
  return {
    id,
    title: id,
    source_id: `source_${id}`,
    document_id: `document_${id}`,
    document_version_id: `version_${id}`,
    status: "queued",
    attempts: 0,
    error_code: null,
    created_at: "2026-07-15T10:00:00Z",
    updated_at: "2026-07-15T10:00:00Z",
  };
}

function Harness({ canRead = false }: { canRead?: boolean }) {
  const state = useKnowledgeDocuments({
    tenantId: "tenant_test",
    spaceId: "space_test",
    canRead,
    query: "",
  });
  return (
    <>
      <button
        onClick={() => {
          state.queueIngestion(ingestion("job_a"), "Policy");
          state.queueIngestion(ingestion("job_b"), "Guide");
        }}
      >
        Queue jobs
      </button>
      {state.ingestionItems.map((item) => (
        <span key={item.id}>{`${item.title}:${item.status}`}</span>
      ))}
    </>
  );
}

afterEach(cleanup);

describe("useKnowledgeDocuments", () => {
  it("tracks and refreshes multiple ingestion jobs independently", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/ingestions/:jobId", ({ params }) =>
        ok({
          ...ingestion(String(params.jobId)),
          status: params.jobId === "job_a" ? "succeeded" : "running",
        }),
      ),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Harness />
      </QueryClientProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Queue jobs" }));

    expect(await screen.findByText("Policy:succeeded")).toBeInTheDocument();
    expect(await screen.findByText("Guide:running")).toBeInTheDocument();
  });

  it("restores active ingestion jobs from the server after a page reload", async () => {
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_test/ingestions", () =>
        ok([{ ...ingestion("job_recovered"), title: "Recovered policy" }]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_test/documents", () =>
        ok([]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/ingestions/job_recovered", () =>
        ok({ ...ingestion("job_recovered"), title: "Recovered policy", status: "running" }),
      ),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <Harness canRead />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Recovered policy:running")).toBeInTheDocument();
  });
});
