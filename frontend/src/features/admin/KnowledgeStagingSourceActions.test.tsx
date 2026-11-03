import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { KnowledgeStagingSourceActions } from "@/features/admin/KnowledgeStagingSourceActions";
import type { KnowledgeSourceActivity } from "@/shared/api/types";

const source: KnowledgeSourceActivity = {
  id: "source_staging",
  title: "Release runbook",
  original_filename: "release.md",
  content_type: "text/markdown",
  size_bytes: 1024,
  change_kind: "create",
  status: "staging",
  document_id: null,
  attempts: 0,
  error_code: null,
  created_by_display_name: "Operator",
  created_by_user: { id: "user_operator", display_name: "Operator", avatar_present: false },
  staging_expires_at: "2026-07-24T01:00:00Z",
  created_at: "2026-07-23T01:00:00Z",
  updated_at: "2026-07-23T01:00:00Z",
};

afterEach(cleanup);

it("retries confirmation and requires confirmation before cleaning a staging upload", async () => {
  const user = userEvent.setup();
  const onCleanup = vi.fn();
  const onRetryConfirmation = vi.fn();
  render(
    <KnowledgeStagingSourceActions
      pendingSourceId={null}
      source={source}
      onCleanup={onCleanup}
      onRetryConfirmation={onRetryConfirmation}
    />,
  );

  await user.click(screen.getByRole("button", { name: "重试确认" }));
  expect(onRetryConfirmation).toHaveBeenCalledWith(source);

  await user.click(screen.getByRole("button", { name: "清理" }));
  expect(onCleanup).not.toHaveBeenCalled();
  await user.click(
    within(await screen.findByRole("tooltip")).getByRole("button", { name: /清\s*理/ }),
  );
  expect(onCleanup).toHaveBeenCalledWith(source);
});
