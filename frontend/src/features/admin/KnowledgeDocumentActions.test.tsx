import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { KnowledgeDocumentActions } from "@/features/admin/KnowledgeDocumentActions";
import type { KnowledgeDocument } from "@/shared/api/types";

const documentOne = {
  id: "document_one",
  status: "active",
  title: "Document one",
} as KnowledgeDocument;
const documentTwo = {
  id: "document_two",
  status: "active",
  title: "Document two",
} as KnowledgeDocument;

it("limits document action loading to the affected row", () => {
  render(
    <>
      <section aria-label="Document one">
        <KnowledgeDocumentActions
          archivingDocumentId={documentOne.id}
          canManage
          document={documentOne}
          downloadingDocumentId={documentOne.id}
          onArchive={vi.fn()}
          onDownload={vi.fn()}
          onReplace={vi.fn()}
          onView={vi.fn()}
        />
      </section>
      <section aria-label="Document two">
        <KnowledgeDocumentActions
          archivingDocumentId={documentOne.id}
          canManage
          document={documentTwo}
          downloadingDocumentId={documentOne.id}
          onArchive={vi.fn()}
          onDownload={vi.fn()}
          onReplace={vi.fn()}
          onView={vi.fn()}
        />
      </section>
    </>,
  );

  const firstRow = screen.getByRole("region", { name: "Document one" });
  const secondRow = screen.getByRole("region", { name: "Document two" });
  expect(actionButton(firstRow, "下载源文件")).toHaveClass("ant-btn-loading");
  expect(actionButton(firstRow, "归档")).toHaveClass("ant-btn-loading");
  expect(actionButton(secondRow, "下载源文件")).not.toHaveClass("ant-btn-loading");
  expect(actionButton(secondRow, "归档")).not.toHaveClass("ant-btn-loading");
});

function actionButton(container: HTMLElement, label: string) {
  const button = within(container).getByText(label).closest("button");
  if (!button) throw new Error(`Action button ${label} is missing`);
  return button;
}
