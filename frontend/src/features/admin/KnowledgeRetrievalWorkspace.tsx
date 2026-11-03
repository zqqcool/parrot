import { useEffect, useState } from "react";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { Button, Empty, Input, Spin, Tag } from "antd";
import { useSearchParams } from "react-router-dom";

import { KnowledgeRetrievalResults } from "@/features/admin/KnowledgeRetrievalResults";
import { KnowledgeRetrievalSettings } from "@/features/admin/KnowledgeRetrievalSettings";
import { adminApi } from "@/shared/api/client";
import type { KnowledgeSearchResult, KnowledgeSpace } from "@/shared/api/types";
import { AppIcon } from "@/shared/icons";
import { RequestErrorAlert } from "@/shared/ui";

type Props = {
  canManage: boolean;
  space: KnowledgeSpace;
  tenantId: string;
  onSettingsUpdated: (space: KnowledgeSpace) => void;
};

export function KnowledgeRetrievalWorkspace({
  canManage,
  space,
  tenantId,
  onSettingsUpdated,
}: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const submittedQuery = normalizeQuery(searchParams.get("query") ?? "");
  const [draft, setDraft] = useState(submittedQuery);
  const search = useQuery({
    queryKey: ["admin", tenantId, "knowledge-space-search", space.id, submittedQuery],
    queryFn: () => adminApi.searchKnowledgeSpace(tenantId, space.id, submittedQuery),
    enabled: Boolean(submittedQuery),
  });

  useEffect(() => setDraft(submittedQuery), [submittedQuery]);

  const normalizedDraft = normalizeQuery(draft);
  const submit = () => {
    if (!normalizedDraft) return;
    if (normalizedDraft === submittedQuery) {
      void search.refetch();
      return;
    }
    setSearchParams({ query: normalizedDraft });
  };

  return (
    <div className="knowledge-retrieval-workspace">
      <RetrievalQueryPanel
        canManage={canManage}
        draft={draft}
        loading={search.isFetching}
        space={space}
        spaceName={space.name}
        tenantId={tenantId}
        onChange={setDraft}
        onSettingsUpdated={onSettingsUpdated}
        onSubmit={submit}
      />
      <RetrievalResultsPanel query={submittedQuery} search={search} tenantId={tenantId} />
    </div>
  );
}

function RetrievalQueryPanel({
  canManage,
  draft,
  loading,
  space,
  spaceName,
  tenantId,
  onChange,
  onSettingsUpdated,
  onSubmit,
}: {
  canManage: boolean;
  draft: string;
  loading: boolean;
  space: KnowledgeSpace;
  spaceName: string;
  tenantId: string;
  onChange: (value: string) => void;
  onSettingsUpdated: (space: KnowledgeSpace) => void;
  onSubmit: () => void;
}) {
  return (
    <aside className="knowledge-retrieval-query-panel" aria-labelledby="retrieval-query-title">
      <header className="knowledge-retrieval-panel-heading">
        <div>
          <h2 id="retrieval-query-title">查询文本</h2>
          <p>输入用户可能提出的问题，测试当前知识库的召回效果。</p>
        </div>
        <Tag color="blue">按配置检索</Tag>
      </header>
      <Input.TextArea
        aria-label="输入问题以测试知识召回"
        autoFocus
        maxLength={1000}
        placeholder="例如：发布流程需要哪些步骤？"
        rows={8}
        showCount
        value={draft}
        onChange={(event) => onChange(event.target.value)}
        onPressEnter={(event) => {
          if (event.metaKey || event.ctrlKey) {
            event.preventDefault();
            onSubmit();
          }
        }}
      />
      <div className="knowledge-retrieval-query-actions">
        <span>按 Ctrl/Cmd + Enter 快速检索</span>
        <Button
          disabled={!normalizeQuery(draft)}
          icon={<AppIcon name="Search" size="md" />}
          loading={loading}
          type="primary"
          onClick={onSubmit}
        >
          开始检索
        </Button>
      </div>
      <RetrievalScope spaceName={spaceName} />
      <KnowledgeRetrievalSettings
        canManage={canManage}
        space={space}
        tenantId={tenantId}
        onUpdated={onSettingsUpdated}
      />
    </aside>
  );
}

function RetrievalScope({ spaceName }: { spaceName: string }) {
  return (
    <>
      <dl className="knowledge-retrieval-scope">
        <div>
          <dt>检索范围</dt>
          <dd>{spaceName}</dd>
        </div>
        <div>
          <dt>内容状态</dt>
          <dd>仅已发布片段</dd>
        </div>
      </dl>
      <p className="knowledge-retrieval-boundary-note">
        关键词检索始终参与召回，最低向量相似度只过滤向量候选，关键词候选不受影响。Embedding
        仅选择模型；还需启用向量检索运行时并完成索引，才会与向量结果融合。结果中的分数是排序分，只用于同次结果内比较，不能与向量阈值直接比较。启用重排序时，会对融合候选继续重排。此测试不会修改
        Agent 绑定，仅测试当前知识库；Agent
        运行时还会合并其绑定的其他知识库，并受单次调用返回条数限制。
      </p>
    </>
  );
}

function RetrievalResultsPanel({
  query,
  search,
  tenantId,
}: {
  query: string;
  search: UseQueryResult<KnowledgeSearchResult[], Error>;
  tenantId: string;
}) {
  return (
    <main className="knowledge-retrieval-results-panel" aria-labelledby="retrieval-results-title">
      <header className="knowledge-retrieval-results-heading">
        <h2 id="retrieval-results-title">
          {search.data ? `${search.data.length} 个召回片段` : "召回结果"}
        </h2>
        <p>
          {search.data?.length
            ? `“${query}” · ${retrievalMethodLabel(search.data[0].retrieval_method)}`
            : "提交查询后，系统会按当前知识空间配置显示匹配片段。"}
        </p>
      </header>
      <KnowledgeRetrievalState query={query} search={search} tenantId={tenantId} />
    </main>
  );
}

function KnowledgeRetrievalState({
  query,
  search,
  tenantId,
}: {
  query: string;
  search: UseQueryResult<KnowledgeSearchResult[], Error>;
  tenantId: string;
}) {
  if (!query) return <RetrievalEmpty description="输入查询内容，查看匹配片段" />;
  if (search.isPending) {
    return (
      <div className="knowledge-retrieval-state" role="status">
        <div className="knowledge-retrieval-loading">
          <Spin />
          <span>正在检索已发布文档…</span>
        </div>
      </div>
    );
  }
  if (search.isError) {
    return (
      <div className="knowledge-retrieval-state knowledge-retrieval-state--error">
        <RequestErrorAlert error={search.error} fallback="知识检索失败" />
      </div>
    );
  }
  if (!search.data?.length) {
    return <RetrievalEmpty description="未找到匹配片段，请调整关键词后重试" />;
  }
  return <KnowledgeRetrievalResults results={search.data} tenantId={tenantId} />;
}

function RetrievalEmpty({ description }: { description: string }) {
  return (
    <div className="knowledge-retrieval-state">
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description} />
    </div>
  );
}

function normalizeQuery(value: string) {
  return value.trim().slice(0, 1000);
}

function retrievalMethodLabel(method: string) {
  const labels: Record<string, string> = {
    lexical: "关键词检索",
    lexical_fallback: "关键词检索（向量不可用）",
    hybrid: "向量 + 关键词融合",
    hybrid_rerank: "向量 + 关键词融合 + 重排序",
    hybrid_rerank_fallback: "向量 + 关键词融合（重排序不可用）",
    hybrid_partial: "混合检索（部分降级）",
  };
  return labels[method] ?? method;
}
