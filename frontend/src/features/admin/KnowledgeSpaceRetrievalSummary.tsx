import { Tag } from "antd";

import type { KnowledgeSpace } from "@/shared/api/types";

export function retrievalPolicy(space: KnowledgeSpace) {
  if (!space.embedding_config_id) return <Tag>关键词检索</Tag>;
  if (space.retrieval_index_status !== "ready") return <Tag color="gold">向量策略（待就绪）</Tag>;
  return (
    <Tag color="cyan">{space.rerank_enabled ? "向量 + 关键词 + 重排序" : "向量 + 关键词"}</Tag>
  );
}

export function embeddingSummary(space: KnowledgeSpace) {
  if (!space.embedding_config_id) return <span className="knowledge-space-muted">未配置</span>;
  const model = space.embedding_config_model ?? space.embedding_config_id;
  const dimension = space.embedding_config_dimension;
  return (
    <span className="knowledge-space-embedding">
      <strong>{model}</strong>
      <span>{dimension ? `${dimension} 维` : "维度未记录"}</span>
    </span>
  );
}

export function indexStatus(space: KnowledgeSpace) {
  const states: Record<
    string,
    { color?: "default" | "error" | "gold" | "success"; label: string }
  > = {
    not_configured: { label: "未配置向量" },
    pending: { color: "gold", label: "等待索引" },
    ready: { color: "success", label: "索引就绪" },
    failed: { color: "error", label: "索引失败" },
  };
  const state = states[space.retrieval_index_status] ?? {
    color: "default" as const,
    label: space.retrieval_index_status,
  };
  return <Tag color={state.color}>{state.label}</Tag>;
}
