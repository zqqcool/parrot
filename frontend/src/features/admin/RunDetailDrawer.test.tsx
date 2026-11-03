import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RunDetailDrawer } from "@/features/admin/RunDetailDrawer";
import { adminApi } from "@/shared/api/client";
import type { Run } from "@/shared/api/types";

vi.mock("@/features/admin/useTenant", () => ({
  useTenantId: () => "tenant_test",
}));

const run: Run = {
  id: "interaction_test",
  tenant_id: "tenant_test",
  agent_id: "agent_test",
  agent_name: "Demo Agent",
  actor_type: "anonymous",
  requester: {
    actor_type: "anonymous",
    actor_id: "visitor_test",
    display_name: "匿名访客",
  },
  entry_type: "text",
  input_type: "text",
  input_summary: "Hello Parrot",
  status: "completed",
  runtime_execution_id: "runtime_test",
  created_at: "2026-07-20T10:00:00Z",
  updated_at: "2026-07-20T10:00:01Z",
};

describe("RunDetailDrawer", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("refreshes every data source displayed in the drawer", async () => {
    const user = userEvent.setup();
    const refreshedRun = deferred<Run>();
    const getRun = vi
      .spyOn(adminApi, "getRun")
      .mockResolvedValueOnce(run)
      .mockReturnValueOnce(refreshedRun.promise);
    const getTaskBoard = vi
      .spyOn(adminApi, "getRunTaskBoard")
      .mockResolvedValue({ id: null, status: "not_generated", tasks: [] });
    const listEvents = vi.spyOn(adminApi, "listRunEvents").mockResolvedValue([]);
    const listDiagnostics = vi.spyOn(adminApi, "listRunDiagnosticTraces").mockResolvedValue([]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <RunDetailDrawer runId={run.id} onClose={() => undefined} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(getRun).toHaveBeenCalledOnce();
      expect(getTaskBoard).toHaveBeenCalledOnce();
      expect(listEvents).toHaveBeenCalledOnce();
      expect(listDiagnostics).toHaveBeenCalledOnce();
    });

    const drawer = await screen.findByRole("dialog", { name: "Run 详情" });
    const header = drawer.querySelector(".ant-drawer-header");
    expect(header).not.toBeNull();
    const refreshButton = within(header as HTMLElement).getByRole("button", {
      name: "刷新 Run 详情",
    });
    await user.click(refreshButton);

    expect(await screen.findByText("正在刷新 Run 详情")).toBeInTheDocument();
    expect(drawer.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    expect(refreshButton).toBeDisabled();

    refreshedRun.resolve(run);

    await waitFor(() => {
      expect(getRun).toHaveBeenCalledTimes(2);
      expect(getTaskBoard).toHaveBeenCalledTimes(2);
      expect(listEvents).toHaveBeenCalledTimes(2);
      expect(listDiagnostics).toHaveBeenCalledTimes(2);
      expect(screen.queryByText("正在刷新 Run 详情")).not.toBeInTheDocument();
      expect(drawer.querySelector('[aria-busy="false"]')).toBeInTheDocument();
      expect(refreshButton).toBeEnabled();
    });
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}
