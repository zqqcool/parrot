import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { codeToTokens, createHighlighterCore } = vi.hoisted(() => {
  const codeToTokens = vi.fn().mockReturnValue({
    bg: "#ffffff",
    fg: "#24292e",
    tokens: [[{ color: "#d73a49", content: "highlighted", offset: 0 }]],
  });
  return {
    codeToTokens,
    createHighlighterCore: vi.fn().mockResolvedValue({ codeToTokens }),
  };
});

vi.mock("shiki/core", () => ({ createHighlighterCore }));
vi.mock("shiki/engine/oniguruma", () => ({ createOnigurumaEngine: vi.fn() }));
vi.mock("shiki/wasm", () => ({}));
vi.mock("@shikijs/themes/github-light", () => ({ default: {} }));
vi.mock("@shikijs/langs/bash", () => ({ default: [] }));
vi.mock("@shikijs/langs/javascript", () => ({ default: [] }));
vi.mock("@shikijs/langs/json", () => ({ default: [] }));
vi.mock("@shikijs/langs/python", () => ({ default: [] }));
vi.mock("@shikijs/langs/typescript", () => ({ default: [] }));
vi.mock("@shikijs/langs/yaml", () => ({ default: [] }));

import { MarkdownPreview } from "@/shared/ui/MarkdownPreview";

describe("MarkdownPreview", () => {
  it("renders GFM, frontmatter, math, and sanitized HTML", () => {
    render(
      <MarkdownPreview
        value={
          "---\nschema_version: 1.0\n---\n\n# Skill guide\n\n| Name | Value |\n| --- | --- |\n| mode | preview |\n\n$x^2$\n\n<strong>safe HTML</strong><script>alert('xss')</script>"
        }
      />,
    );

    expect(screen.getByRole("heading", { name: "Skill guide" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(document.querySelector(".katex")).toBeInTheDocument();
    expect(screen.getByText("safe HTML").tagName).toBe("STRONG");
    expect(screen.queryByText("schema_version: 1.0")).not.toBeInTheDocument();
    expect(screen.queryByText("alert('xss')")).not.toBeInTheDocument();
  });

  it("highlights fenced source code without injecting HTML", async () => {
    render(<MarkdownPreview value={'```json\n{"name": "web-search"}\n```'} />);

    await waitFor(() => {
      expect(document.querySelector(".markdown-code-block__token[style]")).toBeInTheDocument();
    });
    expect(codeToTokens).toHaveBeenCalledWith(
      '{"name": "web-search"}',
      expect.objectContaining({ lang: "json", theme: "github-light" }),
    );
  });
});
