import { StrictMode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentBasicEditor } from "@/features/admin/AgentBasicEditor";
import type { AdminAgent as Agent } from "@/shared/api/types";
import { server } from "@/test/server";

vi.mock("@/shared/uploads", () => ({
  uploadObject: vi.fn(
    ({ file, requestGrant }: { file: File; requestGrant: (metadata: unknown) => unknown }) =>
      requestGrant({ content_type: file.type, size_bytes: file.size }),
  ),
}));

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

const ok = (data: unknown) =>
  HttpResponse.json({ code: "OK", message: "success", data, request_id: "req_test" });

beforeEach(() => {
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:agent-avatar-preview"),
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: vi.fn(),
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  Reflect.deleteProperty(URL, "createObjectURL");
  Reflect.deleteProperty(URL, "revokeObjectURL");
});

describe("AgentBasicEditor", () => {
  it("uploads a selected avatar after saving the supported fields", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onSuccessMessage = vi.fn();
    let updatePayload: unknown;
    let avatarGrantRequested = false;
    let avatarAttachmentRequested = false;
    const updatedAgent = { ...agent, avatar_present: true };
    server.use(
      http.get("/api/v1/admin/agent-types", () =>
        ok([
          {
            key: "knowledge",
            name: "知识型",
            description: "Knowledge agent",
            is_default: true,
          },
        ]),
      ),
      http.patch("/api/v1/admin/tenants/tenant_test/agents/agent_test", async ({ request }) => {
        updatePayload = await request.json();
        return ok(updatedAgent);
      }),
      http.post("/api/v1/admin/tenants/tenant_test/agents/agent_test/avatar-upload-grant", () => {
        avatarGrantRequested = true;
        return ok({
          object_key: "staging/agent-avatars/tenant_test/agent_test/upload_test",
          upload_key: "parrot/staging/agent-avatars/tenant_test/agent_test/upload_test",
          upload_token: "qiniu-upload-token",
          expires_at: "2026-07-13T12:00:00Z",
        });
      }),
      http.put("/api/v1/admin/tenants/tenant_test/agents/agent_test/avatar", () => {
        avatarAttachmentRequested = true;
        return ok(updatedAgent);
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <StrictMode>
        <QueryClientProvider client={client}>
          <AgentBasicEditor
            agent={{ ...agent, avatar_present: true }}
            onClose={onClose}
            onSuccessMessage={onSuccessMessage}
            open
            tenantId="tenant_test"
          />
        </QueryClientProvider>
      </StrictMode>,
    );

    const editor = await screen.findByRole("dialog", { name: "编辑基本资料" });
    const avatarButton = within(editor).getByRole("button", { name: "选择头像" });
    const nameInput = within(editor).getByRole("textbox", { name: "名称" });
    expect(avatarButton.compareDocumentPosition(nameInput) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(avatarButton.querySelector("img")).toHaveAttribute(
      "src",
      "/api/v1/admin/tenants/tenant_test/agents/agent_test/avatar",
    );
    const input = editor.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    await user.upload(input!, new File(["avatar"], "avatar.png", { type: "image/png" }));
    await waitFor(() =>
      expect(avatarButton.querySelector("img")).toHaveAttribute("src", "blob:agent-avatar-preview"),
    );
    await user.click(within(editor).getByRole("button", { name: /保\s*存/ }));

    await waitFor(() => expect(avatarGrantRequested).toBe(true));
    await waitFor(() => expect(avatarAttachmentRequested).toBe(true));
    expect(updatePayload).toEqual({
      agent_type_key: "knowledge",
      description: "Demo",
      name: "Demo Agent",
    });
    expect(onSuccessMessage).toHaveBeenCalledWith("智能体信息和头像已保存");
    expect(onClose).toHaveBeenCalledOnce();
  });
});
