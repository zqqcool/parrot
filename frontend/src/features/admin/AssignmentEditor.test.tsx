import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AssignmentEditor } from "@/features/admin/AssignmentEditor";

describe("AssignmentEditor", () => {
  it("loads the current assignment before submitting a replacement", async () => {
    const user = userEvent.setup();
    const load = vi.fn().mockResolvedValue({ ids: ["role_viewer"] });
    const save = vi.fn().mockResolvedValue({ updated: true });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <AssignmentEditor
          open
          title="Roles for Alex"
          queryKey={["assignment", "alex"]}
          options={[{ value: "role_viewer", label: "Viewer" }]}
          load={load}
          save={save}
          onClose={() => undefined}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(load).toHaveBeenCalledOnce());
    expect(await screen.findByText("Viewer")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "OK" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0]?.[0]).toEqual(["role_viewer"]);
  });
});
