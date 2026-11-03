import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { KnowledgeDocumentsHeading } from "@/features/admin/KnowledgeDocumentsHeading";

const space = {
  id: "space_test",
  name: "Engineering",
} as Parameters<typeof KnowledgeDocumentsHeading>[0]["space"];

it("emphasizes retrieval testing without competing with the primary document action", async () => {
  const user = userEvent.setup();
  const onOpenSearch = vi.fn();
  render(
    <KnowledgeDocumentsHeading
      canManage
      canQuery
      space={space}
      onOpenAdd={vi.fn()}
      onOpenSearch={onOpenSearch}
    />,
  );

  const searchButton = screen.getByRole("button", { name: "检索测试" });
  expect(searchButton).toHaveClass("ant-btn-primary", "ant-btn-background-ghost");
  expect(screen.getByRole("button", { name: "添加文档" })).toHaveClass("ant-btn-primary");

  await user.click(searchButton);
  expect(onOpenSearch).toHaveBeenCalledOnce();
});
