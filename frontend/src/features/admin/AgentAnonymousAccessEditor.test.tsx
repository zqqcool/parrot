import { StrictMode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentAnonymousAccessEditor } from "@/features/admin/AgentAnonymousAccessEditor";
import type { AdminAgent as Agent } from "@/shared/api/types";

const agent: Agent = {
  id: "agent_test",
  tenant_id: "tenant_test",
  runtime_agent_id: "runtime_test",
  slug: "demo-agent",
  name: "Demo Agent",
  description: "Demo",
  system_prompt: "You are a concise assistant.",
  capability_relevance_threshold: 0.4,
  status: "active",
  agent_type_key: "knowledge",
  published: true,
  allow_anonymous: true,
  avatar_present: false,
};

afterEach(() => cleanup());

describe("AgentAnonymousAccessEditor", () => {
  it("restores the existing access setting in React Strict Mode", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <StrictMode>
        <QueryClientProvider client={client}>
          <AgentAnonymousAccessEditor
            agent={agent}
            onClose={vi.fn()}
            onSuccessMessage={vi.fn()}
            open
            tenantId="tenant_test"
          />
        </QueryClientProvider>
      </StrictMode>,
    );

    const editor = await screen.findByRole("dialog", { name: "调整匿名访问" });
    expect(within(editor).getByRole("checkbox", { name: "允许匿名访问" })).toBeChecked();
  });
});
