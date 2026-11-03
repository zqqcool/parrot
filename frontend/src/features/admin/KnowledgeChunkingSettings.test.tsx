import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { KnowledgeChunkingSettings } from "@/features/admin/KnowledgeChunkingSettings";
import type { KnowledgeSpace } from "@/shared/api/types";

const space = {
  id: "space_test",
  chunk_separator: "\\n\\n",
  chunk_size_chars: 2000,
  chunk_overlap_chars: 200,
  text_processing: { normalize_whitespace: true, remove_urls_and_emails: true },
} as KnowledgeSpace;

it("groups chunking rules and retrieval text cleaning in the configuration dialog", async () => {
  const user = userEvent.setup();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <KnowledgeChunkingSettings
        canManage
        space={space}
        tenantId="tenant_test"
        onUpdated={vi.fn()}
      />
    </QueryClientProvider>,
  );

  await user.click(screen.getByRole("button", { name: "调整切分配置" }));
  const dialog = await screen.findByRole("dialog", { name: "调整切分配置" });

  expect(within(dialog).getByRole("heading", { name: "切分规则" })).toBeInTheDocument();
  expect(within(dialog).getByRole("heading", { name: "检索文本清洗" })).toBeInTheDocument();
  expect(within(dialog).getByLabelText("规整空白与段落")).toBeChecked();
  expect(within(dialog).getByLabelText("移除 URL 和邮箱")).toBeChecked();
  expect(
    within(dialog).getByRole("spinbutton", { name: "单块目标字符数" }).closest(".ant-input-number"),
  ).toHaveStyle({ width: "100%" });
  expect(
    within(dialog)
      .getByRole("spinbutton", { name: "相邻块重叠字符数" })
      .closest(".ant-input-number"),
  ).toHaveStyle({ width: "100%" });
});
