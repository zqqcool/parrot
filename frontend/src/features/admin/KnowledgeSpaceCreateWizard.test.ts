import { beforeEach, describe, expect, it, vi } from "vitest";

describe("KnowledgeSpaceCreateWizard route assets", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("loads the knowledge page styles when opened as a direct route", async () => {
    const styleLoaded = vi.fn();
    vi.doMock("@/features/admin/knowledge-page.css", () => {
      styleLoaded();
      return {};
    });

    await import("@/features/admin/KnowledgeSpaceCreateWizard");

    expect(styleLoaded).toHaveBeenCalledOnce();
  });
});
