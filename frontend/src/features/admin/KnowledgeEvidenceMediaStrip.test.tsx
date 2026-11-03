import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import type { ReactElement } from "react";
import { StrictMode } from "react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { KnowledgeEvidenceMediaStrip } from "@/features/admin/KnowledgeEvidenceMediaStrip";
import { KnowledgeRetrievalResults } from "@/features/admin/KnowledgeRetrievalResults";
import {
  mediaGroupLabel,
  mediaRefLabel,
  orderMediaRefs,
} from "@/features/admin/knowledgeMediaOrder";
import type { KnowledgeSearchResult } from "@/shared/api/types";
import { server } from "@/test/server";

const createObjectUrl = vi.fn(() => "blob:knowledge-media-preview");
const revokeObjectUrl = vi.fn();

beforeEach(() => {
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: createObjectUrl,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: revokeObjectUrl,
  });
});

afterEach(() => {
  cleanup();
  Reflect.deleteProperty(URL, "createObjectURL");
  Reflect.deleteProperty(URL, "revokeObjectURL");
  vi.clearAllMocks();
});

const pngBytes = Uint8Array.from([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
  0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
  0xde, 0x00, 0x00, 0x00, 0x0c, 0x49, 0x44, 0x41, 0x54, 0x08, 0xd7, 0x63, 0xf8, 0xcf, 0xc0, 0x00,
  0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x05, 0xfe, 0xd4, 0xef, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,
  0x4e, 0x44, 0xae, 0x42, 0x60, 0x82,
]);

function result(overrides: Partial<KnowledgeSearchResult> = {}): KnowledgeSearchResult {
  return {
    chunk_id: "chunk_test",
    document_id: "document_test",
    document_version_id: "version_test",
    title: "Operation manual",
    citation_anchor: "slide-3",
    content_chars: 42,
    score: 1 / 61,
    excerpt: "Click Sign in with SSO",
    excerpt_truncated: false,
    retrieval_method: "hybrid",
    match_sources: ["lexical", "vector"],
    vector_score: 0.9,
    embedding_config_name: "Embedding",
    reranker_config_name: null,
    degradation_reason: null,
    slide_no: 3,
    media_refs: [
      { asset_id: "media_b", asset_kind: "slide_render", ordinal: 0, slide_no: 4 },
      { asset_id: "media_a", asset_kind: "slide_render", ordinal: 0, slide_no: 3 },
    ],
    ...overrides,
  };
}

function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("knowledge evidence media strip", () => {
  it("orders media refs by slide then ordinal", () => {
    expect(
      orderMediaRefs([
        { asset_id: "b", asset_kind: "slide_render", ordinal: 1, slide_no: 2 },
        { asset_id: "a", asset_kind: "slide_render", ordinal: 0, slide_no: 2 },
        { asset_id: "c", asset_kind: "slide_render", ordinal: 0, slide_no: 1 },
      ]).map((item) => item.asset_id),
    ).toEqual(["c", "a", "b"]);
  });

  it("preserves Office locators for labels and ordering", () => {
    const refs = orderMediaRefs([
      {
        asset_id: "section",
        asset_kind: "embedded",
        ordinal: 0,
        section_path: "3. Login / 3.1 SSO",
      },
      {
        asset_id: "sheet-b",
        asset_kind: "embedded",
        ordinal: 1,
        sheet_name: "Orders",
        cell_anchor: "Orders!C20",
      },
      {
        asset_id: "sheet-a",
        asset_kind: "embedded",
        ordinal: 0,
        sheet_name: "Orders",
        cell_anchor: "Orders!C2",
      },
    ]);

    expect(refs.map((item) => item.asset_id)).toEqual(["sheet-a", "sheet-b", "section"]);
    expect(mediaGroupLabel(null, refs)).toBe("关联工作表 Orders");
    expect(mediaRefLabel(refs[0])).toBe("Orders!C2");
    expect(mediaRefLabel(refs[2])).toBe("章节 3. Login / 3.1 SSO");
  });

  it("labels fallback thumbnails as degraded previews", () => {
    expect(
      mediaRefLabel({
        asset_id: "fallback",
        asset_kind: "thumb",
        ordinal: 0,
        slide_no: 5,
      }),
    ).toBe("第 5 页（降级预览）");
  });

  it("renders ordered slide previews from authorized media downloads", async () => {
    const requested: string[] = [];
    server.use(
      http.get("/api/v1/admin/tenants/:tenantId/knowledge/media/:assetId/content", ({ params }) => {
        requested.push(String(params.assetId));
        return new HttpResponse(pngBytes, {
          headers: {
            "Content-Type": "image/png",
            "Content-Disposition": "inline; filename*=UTF-8''slide.png",
          },
        });
      }),
    );

    renderWithQuery(
      <StrictMode>
        <KnowledgeEvidenceMediaStrip
          mediaRefs={result().media_refs}
          slideNo={3}
          tenantId="tenant_test"
        />
      </StrictMode>,
    );

    expect(screen.getByLabelText("关联幻灯片 3 · 4")).toBeInTheDocument();
    await waitFor(() => expect(requested.length).toBeGreaterThanOrEqual(2));
    expect(requested).toEqual(expect.arrayContaining(["media_a", "media_b"]));
    expect(await screen.findByAltText("第 3 页")).toBeInTheDocument();
    expect(screen.getByAltText("第 4 页")).toBeInTheDocument();
    // StrictMode double-invokes effects; create must outlive revoke for the live URL.
    expect(createObjectUrl).toHaveBeenCalled();
    expect(revokeObjectUrl).toHaveBeenCalled();
  });

  it("hides the strip when a result has no media refs", () => {
    const { container } = renderWithQuery(
      <KnowledgeRetrievalResults
        results={[result({ media_refs: [], slide_no: null })]}
        tenantId="tenant_test"
      />,
    );
    expect(container.querySelector(".knowledge-evidence-media-strip")).toBeNull();
    expect(screen.queryByText(/^幻灯片 /)).not.toBeInTheDocument();
  });
});
