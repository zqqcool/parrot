import { StrictMode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentSystemPromptEditor } from "@/features/admin/AgentSystemPromptEditor";
import type { AdminAgent as Agent } from "@/shared/api/types";

const agent: Agent = {
  id: "agent_test",
  tenant_id: "tenant_test",
  runtime_agent_id: "runtime_test",
  slug: "demo-agent",
  name: "Demo Agent",
  description: "Demo",
  system_prompt: "# Agent guide\n\n<script>alert('xss')</script>",
  capability_relevance_threshold: 0.4,
  status: "active",
  agent_type_key: "knowledge",
  published: true,
  allow_anonymous: true,
  avatar_present: false,
};

afterEach(() => cleanup());

describe("AgentSystemPromptEditor", () => {
  it("previews the system prompt as safe Markdown", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <StrictMode>
        <QueryClientProvider client={client}>
          <AgentSystemPromptEditor
            agent={agent}
            onClose={vi.fn()}
            onSuccessMessage={vi.fn()}
            open
            tenantId="tenant_test"
          />
        </QueryClientProvider>
      </StrictMode>,
    );

    const editor = await screen.findByRole("dialog", { name: "编辑系统提示词" });
    expect(within(editor).getByRole("textbox", { name: "系统提示词" })).toHaveValue(
      agent.system_prompt,
    );
    const previewLabel = within(editor).getByRole("radio", { name: "预览" }).closest("label");
    expect(previewLabel).not.toBeNull();
    await user.click(previewLabel!);

    expect(within(editor).getByRole("heading", { name: "Agent guide" })).toBeInTheDocument();
    expect(within(editor).queryByText("alert('xss')")).not.toBeInTheDocument();
  });
});
