import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { KnowledgeRetrievalResults } from "@/features/admin/KnowledgeRetrievalResults";
import { KnowledgeRetrievalSettingsForm } from "@/features/admin/KnowledgeRetrievalSettingsForm";
import type { KnowledgeSearchResult, KnowledgeSpaceRetrievalUpdate } from "@/shared/api/types";

const settings: KnowledgeSpaceRetrievalUpdate = {
  embedding_config_id: "embedding_test",
  candidate_top_k: 20,
  min_vector_score: 0.6,
  rerank_enabled: false,
  reranker_config_id: null,
  rerank_top_n: 10,
  min_rerank_score: null,
};

const result: KnowledgeSearchResult = {
  chunk_id: "chunk_test",
  document_id: "document_test",
  document_version_id: "version_test",
  title: "Quality gates",
  citation_anchor: "chunk-1",
  content_chars: 42,
  score: 1 / 61,
  excerpt: "Run the quality checks before release.",
  excerpt_truncated: false,
  retrieval_method: "hybrid",
  match_sources: ["lexical", "vector"],
  vector_score: 0.9,
  embedding_config_name: "Embedding",
  reranker_config_name: null,
  degradation_reason: null,
  slide_no: null,
  media_refs: [],
};

describe("knowledge retrieval score semantics", () => {
  it("explains that the vector threshold does not filter lexical candidates", () => {
    render(
      <KnowledgeRetrievalSettingsForm
        error={null}
        initialValues={settings}
        loading={false}
        rerankerError={null}
        rerankers={[]}
        onSubmit={() => undefined}
      />,
    );

    expect(screen.getByText(/最低向量相似度只过滤向量候选/)).toBeInTheDocument();
    expect(screen.getByText(/结果展示的是融合排序分/)).toBeInTheDocument();
    expect(screen.getByText("最低向量相似度（可选）")).toBeInTheDocument();
    expect(screen.getByText("多模态 Embedding（预留）")).toBeInTheDocument();
  });

  it("labels hybrid scores as fusion ranking scores", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <KnowledgeRetrievalResults results={[result]} tenantId="tenant_test" />
      </QueryClientProvider>,
    );

    expect(screen.getByText("融合排序分 0.016")).toBeInTheDocument();
    expect(screen.getByText("关键词 + 向量命中")).toBeInTheDocument();
    expect(screen.getByText("向量相似度 0.900")).toBeInTheDocument();
  });

  it("identifies a lexical-only result without showing a vector similarity", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const view = render(
      <QueryClientProvider client={client}>
        <KnowledgeRetrievalResults
          results={[{ ...result, match_sources: ["lexical"], vector_score: null }]}
          tenantId="tenant_test"
        />
      </QueryClientProvider>,
    );

    expect(within(view.container).getByText("关键词命中")).toBeInTheDocument();
    expect(within(view.container).queryByText(/^向量相似度/)).not.toBeInTheDocument();
  });
});
