import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/shared/ui/monaco", () => ({}));
vi.mock("@monaco-editor/react", () => ({
  default: ({ language, value }: { language: string; value: string }) => (
    <div data-testid="code-preview">{`${language}:${value}`}</div>
  ),
}));

import { WorkspaceLargePreview } from "@/shared/ui/WorkspaceLargePreview";

describe("WorkspaceLargePreview", () => {
  it("renders the active Markdown file in a large preview", () => {
    render(
      <WorkspaceLargePreview
        file={{ path: "SKILL.md", content: "# Web search" }}
        open
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByText("SKILL.md · 大屏预览")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Markdown 预览")).toHaveTextContent("Web search");
  });

  it("renders non-Markdown files as read-only code", () => {
    render(
      <WorkspaceLargePreview
        file={{ path: "skyler.manifest.json", content: '{"schema_version":"1.0"}' }}
        open
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByTestId("code-preview")).toHaveTextContent('json:{"schema_version":"1.0"}');
  });
});
