import { describe, expect, it } from "vitest";

import {
  knowledgeDocumentTitleFromFile,
  knowledgeUploadContentType,
} from "@/features/admin/knowledgeUpload";

describe("knowledge upload files", () => {
  it("normalizes the server-supported file types by extension", () => {
    expect(knowledgeUploadContentType("policy.PDF")).toBe("application/pdf");
    expect(knowledgeUploadContentType("release.docx")).toBe(
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    );
    expect(knowledgeUploadContentType("manual.pptx")).toBe(
      "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    );
    expect(knowledgeUploadContentType("matrix.xlsx")).toBe(
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    );
    expect(knowledgeUploadContentType("runbook.md")).toBe("text/markdown");
    expect(knowledgeUploadContentType("notes.txt")).toBe("text/plain");
    expect(knowledgeUploadContentType("scan.png")).toBeNull();
  });

  it("uses the filename without its last extension as the document title", () => {
    expect(knowledgeDocumentTitleFromFile("release.v2.md")).toBe("release.v2");
    expect(knowledgeDocumentTitleFromFile("README")).toBe("README");
  });
});
