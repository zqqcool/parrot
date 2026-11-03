import { useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { message } from "antd";

import { adminApi } from "@/shared/api/client";
import type { KnowledgeSpace, KnowledgeSpaceRetrievalUpdate } from "@/shared/api/types";

import { KnowledgeRetrievalSettingsForm } from "./KnowledgeRetrievalSettingsForm";

type Props = {
  canManage: boolean;
  space: KnowledgeSpace;
  tenantId: string;
  onUpdated: (space: KnowledgeSpace) => void;
};

export function KnowledgeRetrievalSettings({ canManage, space, tenantId, onUpdated }: Props) {
  const [messageApi, messageContext] = message.useMessage();
  const semanticEnabled = Boolean(space.embedding_config_id);
  const initialValues = useMemo(() => retrievalSettings(space), [space]);
  const rerankers = useQuery({
    queryKey: ["admin", tenantId, "reranker-configs"],
    queryFn: () => adminApi.listRerankerConfigs(tenantId),
    enabled: canManage && semanticEnabled,
  });
  const update = useMutation({
    mutationFn: (payload: KnowledgeSpaceRetrievalUpdate) =>
      adminApi.updateKnowledgeSpaceRetrieval(tenantId, space.id, payload),
    onSuccess: (updated) => {
      onUpdated(updated);
      void messageApi.success("检索参数已保存");
    },
  });
  const rerankerName = configName(rerankers.data, space.reranker_config_id);

  return (
    <section className="knowledge-chunking-settings" aria-labelledby="knowledge-retrieval-heading">
      {messageContext}
      <div>
        <h3 id="knowledge-retrieval-heading">检索参数</h3>
        <p>
          保存后，召回测试和 Agent 混合检索会使用相同的候选 Top
          K、最低向量相似度与重排序设置；Embedding 模式在创建后保持锁定。
        </p>
      </div>
      <dl className="knowledge-chunking-values">
        <div>
          <dt>当前模式</dt>
          <dd>{retrievalMode(space)}</dd>
        </div>
        <div>
          <dt>Embedding</dt>
          <dd>{embeddingSummary(space)}</dd>
        </div>
        <div>
          <dt>候选 Top K</dt>
          <dd>{space.candidate_top_k}</dd>
        </div>
        <div>
          <dt>索引状态</dt>
          <dd>{indexStatus(space)}</dd>
        </div>
        {space.rerank_enabled ? (
          <div>
            <dt>重排序</dt>
            <dd>{rerankerName ?? "配置已不可见"}</dd>
          </div>
        ) : null}
      </dl>
      {canManage ? (
        semanticEnabled ? (
          <KnowledgeRetrievalSettingsForm
            error={update.error}
            initialValues={initialValues}
            loading={update.isPending}
            rerankerError={rerankers.error}
            rerankers={activeConfigs(rerankers.data)}
            onSubmit={update.mutate}
          />
        ) : (
          <p className="knowledge-retrieval-settings-notice" role="note">
            纯词法检索不会调用外部 Embedding 或重排序服务。
          </p>
        )
      ) : null}
    </section>
  );
}

function retrievalSettings(space: KnowledgeSpace): KnowledgeSpaceRetrievalUpdate {
  return {
    embedding_config_id: space.embedding_config_id,
    candidate_top_k: space.candidate_top_k,
    min_vector_score: space.min_vector_score,
    rerank_enabled: space.rerank_enabled,
    reranker_config_id: space.reranker_config_id,
    rerank_top_n: space.rerank_top_n,
    min_rerank_score: space.min_rerank_score,
  };
}

function activeConfigs<T extends { status: string }>(configs: T[] | undefined): T[] {
  return (configs ?? []).filter((config) => config.status === "active");
}

function configName<T extends { id: string; name: string }>(
  configs: T[] | undefined,
  id: string | null,
) {
  return configs?.find((config) => config.id === id)?.name ?? id ?? undefined;
}

function retrievalMode(space: KnowledgeSpace): string {
  if (!space.embedding_config_id) return "纯词法";
  return space.rerank_enabled ? "向量 + 重排序" : "向量 + 词法融合";
}

function embeddingSummary(space: KnowledgeSpace): string {
  if (!space.embedding_config_id) return "纯词法（已锁定）";
  const model = space.embedding_config_model ?? space.embedding_config_id;
  const dimension = space.embedding_config_dimension;
  return dimension ? `${model}（${dimension} 维，已锁定）` : `${model}（已锁定）`;
}

function indexStatus(space: KnowledgeSpace): string {
  const labels: Record<string, string> = {
    not_configured: "未配置",
    pending: "等待索引",
    ready: "就绪",
    failed: "失败",
  };
  return `${labels[space.retrieval_index_status] ?? space.retrieval_index_status}（v${space.retrieval_index_revision}）`;
}
