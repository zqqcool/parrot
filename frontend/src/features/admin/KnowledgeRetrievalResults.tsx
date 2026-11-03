import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, List, Tag, Tooltip } from "antd";

import { KnowledgeEvidenceMediaStrip } from "@/features/admin/KnowledgeEvidenceMediaStrip";
import { mediaRefLabel } from "@/features/admin/knowledgeMediaOrder";
import { adminApi } from "@/shared/api/client";
import type { KnowledgeMediaRef, KnowledgeSearchResult } from "@/shared/api/types";
import { AppIcon } from "@/shared/icons";
import { RequestErrorAlert } from "@/shared/ui";

type ResultsProps = {
  results: KnowledgeSearchResult[];
  tenantId: string;
};

export function KnowledgeRetrievalResults({ results, tenantId }: ResultsProps) {
  return (
    <List
      className="knowledge-retrieval-results"
      dataSource={results}
      rowKey="chunk_id"
      split={false}
      renderItem={(result, index) => (
        <KnowledgeRetrievalResultCard index={index} result={result} tenantId={tenantId} />
      )}
    />
  );
}

type ResultCardProps = {
  index: number;
  result: KnowledgeSearchResult;
  tenantId: string;
};

function KnowledgeRetrievalResultCard({ index, result, tenantId }: ResultCardProps) {
  const expansion = useCitationExpansion(tenantId, result);
  const expandable = result.excerpt_truncated || isVisuallyLong(result.excerpt);
  const mediaRefs =
    expansion.mediaRefs.length > 0 ? expansion.mediaRefs : (result.media_refs ?? []);
  const locator = resultLocator(result, mediaRefs);

  return (
    <List.Item className="knowledge-retrieval-result-card">
      <div className="knowledge-retrieval-result-meta">
        <div>
          <strong>片段 {String(index + 1).padStart(2, "0")}</strong>
          <span>{result.content_chars.toLocaleString()} 字符</span>
          {locator == null ? null : <span>{locator}</span>}
        </div>
        <div className="knowledge-retrieval-result-tags">
          <Tooltip title="RRF 排序分仅用于同一次结果内比较，不代表向量相似度、百分比或模型置信度。">
            <span tabIndex={0}>
              <Tag color="blue">
                {scoreLabel(result.retrieval_method)} {formatScore(result.score)}
              </Tag>
            </span>
          </Tooltip>
          <Tag color={matchSourceColor(result)}>{matchSourceLabel(result)}</Tag>
          {result.vector_score == null ? null : (
            <Tag color="purple">向量相似度 {formatVectorScore(result.vector_score)}</Tag>
          )}
        </div>
      </div>
      <p
        className={`knowledge-retrieval-result-excerpt${expansion.contentExpanded ? " is-expanded" : ""}`}
      >
        {expansion.content}
      </p>
      <KnowledgeEvidenceMediaStrip
        mediaRefs={mediaRefs}
        slideNo={result.slide_no}
        tenantId={tenantId}
      />
      {expansion.error ? (
        <div className="knowledge-retrieval-result-expansion-error">
          <RequestErrorAlert
            error={expansion.error}
            fallback="加载完整片段失败；请收起片段后重试"
          />
        </div>
      ) : null}
      {expandable ? (
        <Button
          aria-expanded={expansion.contentExpanded}
          className="knowledge-retrieval-result-toggle"
          loading={expansion.loading}
          size="small"
          type="link"
          onClick={expansion.toggle}
        >
          {toggleLabel({
            expanded: expansion.expanded,
            loading: expansion.loading,
            needsFullContent: result.excerpt_truncated,
          })}
        </Button>
      ) : null}
      <footer className="knowledge-retrieval-result-source">
        <AppIcon name="FileText" size="md" />
        <strong>{result.title}</strong>
        <span>{result.citation_anchor}</span>
      </footer>
      {result.degradation_reason ? (
        <p className="knowledge-retrieval-result-degradation">
          {degradationReasonLabel(result.degradation_reason)}
        </p>
      ) : null}
    </List.Item>
  );
}

function resultLocator(result: KnowledgeSearchResult, mediaRefs: readonly KnowledgeMediaRef[]) {
  if (result.slide_no != null) return `第 ${result.slide_no} 页`;
  return mediaRefs[0] ? mediaRefLabel(mediaRefs[0]) : null;
}

function useCitationExpansion(tenantId: string, result: KnowledgeSearchResult) {
  const [expanded, setExpanded] = useState(false);
  const [requestSequence, setRequestSequence] = useState(0);
  const needsFullContent = result.excerpt_truncated;
  const citation = useQuery({
    queryKey: ["admin", tenantId, "knowledge-citation", result.chunk_id, requestSequence],
    queryFn: () => adminApi.expandKnowledgeCitation(tenantId, result.chunk_id),
    enabled: expanded && needsFullContent,
    gcTime: 0,
    retry: false,
  });
  const fullContentReady = !needsFullContent || citation.isSuccess;
  const contentExpanded = expanded && fullContentReady;
  const content = contentExpanded && citation.data ? citation.data.content : result.excerpt;

  const toggle = () => {
    if (expanded) {
      setExpanded(false);
      return;
    }
    if (needsFullContent) setRequestSequence((current) => current + 1);
    setExpanded(true);
  };

  return {
    content,
    contentExpanded,
    error: citation.isError && expanded ? citation.error : null,
    expanded,
    loading: citation.isFetching,
    mediaRefs: citation.data?.media_refs ?? [],
    toggle,
  };
}

function isVisuallyLong(value: string) {
  return value.length > 360 || value.split("\n").length > 8;
}

function toggleLabel({
  expanded,
  loading,
  needsFullContent,
}: {
  expanded: boolean;
  loading: boolean;
  needsFullContent: boolean;
}) {
  if (loading) return "正在加载完整片段";
  if (expanded) return "收起片段";
  return needsFullContent ? "查看完整片段" : "展开片段";
}

function formatScore(score: number) {
  return score.toFixed(score < 0.01 ? 4 : 3);
}

function formatVectorScore(score: number) {
  return score.toFixed(3);
}

function scoreLabel(method: string) {
  return method === "lexical" || method === "lexical_fallback" ? "排序分" : "融合排序分";
}

function retrievalMethodLabel(method: string) {
  const labels: Record<string, string> = {
    lexical: "关键词检索",
    lexical_fallback: "关键词检索降级",
    hybrid: "向量 + 关键词",
    hybrid_rerank: "向量 + 关键词 + 重排序",
    hybrid_rerank_fallback: "向量 + 关键词",
    hybrid_partial: "混合检索",
  };
  return labels[method] ?? method;
}

function matchSourceLabel(result: KnowledgeSearchResult) {
  const lexical = result.match_sources?.includes("lexical");
  const vector = result.match_sources?.includes("vector");
  if (lexical && vector) return "关键词 + 向量命中";
  if (vector) return "向量命中";
  if (lexical) return "关键词命中";
  return retrievalMethodLabel(result.retrieval_method);
}

function matchSourceColor(result: KnowledgeSearchResult) {
  const lexical = result.match_sources?.includes("lexical");
  const vector = result.match_sources?.includes("vector");
  if (lexical && vector) return "cyan";
  if (vector) return "purple";
  return "default";
}

function degradationReasonLabel(reason: string) {
  const labels: Record<string, string> = {
    vector_runtime_unavailable: "向量检索运行时未配置完成，当前使用关键词检索。",
    vector_index_not_ready: "向量索引尚未就绪，当前使用关键词检索。",
    embedding_config_unavailable: "Embedding 配置不可用，当前使用关键词检索。",
    embedding_config_snapshot_mismatch: "Embedding 配置与索引快照不一致，当前使用关键词检索。",
    embedding_or_vector_service_unavailable: "Embedding 或向量服务暂不可用，当前使用关键词检索。",
    reranker_config_unavailable: "重排序配置不可用，保留融合排序结果。",
    reranker_service_unavailable: "重排序服务暂不可用，保留融合排序结果。",
  };
  return labels[reason] ?? "当前检索链路部分不可用，已使用可用的候选结果。";
}
