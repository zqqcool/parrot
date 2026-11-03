import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Input, InputNumber, Modal } from "antd";

import { KnowledgeEvidenceMediaStrip } from "@/features/admin/KnowledgeEvidenceMediaStrip";
import { mediaRefLabel } from "@/features/admin/knowledgeMediaOrder";
import { adminApi } from "@/shared/api/client";
import type { AgentKnowledgeSearchTest } from "@/shared/api/types";
import { DataTable, RequestErrorAlert } from "@/shared/ui";

type Props = {
  agentId: string;
  open: boolean;
  tenantId: string;
  onClose: () => void;
};

export function AgentKnowledgeSearchTest({ agentId, open, tenantId, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(6);
  const test = useMutation({
    mutationFn: () => adminApi.testAgentKnowledgeSearch(tenantId, agentId, { query, limit }),
  });
  const close = () => {
    if (!test.isPending) onClose();
  };

  return (
    <Modal
      classNames={{ body: "agent-knowledge-search-test-modal-body" }}
      closable={!test.isPending}
      destroyOnHidden
      footer={
        <Button disabled={test.isPending} onClick={close}>
          关闭
        </Button>
      }
      keyboard={!test.isPending}
      maskClosable={!test.isPending}
      open={open}
      title="真实工具检索测试"
      width={1200}
      afterOpenChange={(visible) => {
        if (visible) return;
        setQuery("");
        setLimit(6);
        test.reset();
      }}
      onCancel={close}
    >
      <div className="agent-knowledge-search-test">
        <p>以当前 Agent 的知识库绑定和每个知识库的检索策略执行 knowledge_search，不会调用 LLM。</p>
        <div className="agent-knowledge-search-test-controls">
          <Input.TextArea
            aria-label="检索问题"
            autoSize={{ minRows: 2, maxRows: 5 }}
            maxLength={1000}
            placeholder="输入用户可能向 Agent 提出的问题"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <label className="agent-knowledge-search-limit">
            <span>返回条数</span>
            <InputNumber
              aria-label="返回条数"
              min={1}
              max={12}
              value={limit}
              onChange={(value) => setLimit(value ?? 6)}
            />
          </label>
          <Button
            disabled={!query.trim() || test.isPending}
            loading={test.isPending}
            type="primary"
            onClick={() => test.mutate()}
          >
            开始真实检索
          </Button>
        </div>
        <RequestErrorAlert error={test.error} fallback="执行真实工具检索失败" />
        {test.data ? <SearchTestResult result={test.data} tenantId={tenantId} /> : null}
      </div>
    </Modal>
  );
}

function SearchTestResult({
  result,
  tenantId,
}: {
  result: AgentKnowledgeSearchTest;
  tenantId: string;
}) {
  const message = `状态：${result.status}；检索方式：${result.retrieval_method}；候选片段：${result.candidate_count}；耗时：${result.duration_ms} ms`;
  return (
    <div className="agent-knowledge-search-test-result">
      <Alert
        showIcon
        type={result.status === "ok" ? "success" : "warning"}
        message={message}
        description={
          result.status === "degraded"
            ? `受影响空间会单独回退为词法检索：${result.degradation_reasons.join("、")}`
            : undefined
        }
      />
      <DataTable<(typeof result.items)[number]>
        rowKey="citation_id"
        dataSource={result.items}
        locale={{ emptyText: "未找到匹配片段" }}
        pagination={false}
        scroll={{ x: 1400 }}
        expandable={{
          rowExpandable: (item) => (item.media_refs?.length ?? 0) > 0,
          expandedRowRender: (item) => (
            <KnowledgeEvidenceMediaStrip
              mediaRefs={item.media_refs ?? []}
              slideNo={item.slide_no}
              tenantId={tenantId}
            />
          ),
        }}
        columns={[
          { title: "知识空间", dataIndex: "space_id", width: 160, ellipsis: true },
          { title: "来源", dataIndex: "title", width: 180, ellipsis: true },
          {
            title: "定位",
            key: "locator",
            width: 150,
            ellipsis: true,
            render: (_, item) =>
              item.slide_no != null
                ? `第 ${item.slide_no} 页`
                : item.media_refs?.[0]
                  ? mediaRefLabel(item.media_refs[0])
                  : "—",
          },
          { title: "检索方式", dataIndex: "retrieval_method", width: 150 },
          {
            title: "模型配置",
            key: "config",
            width: 210,
            ellipsis: true,
            render: (_, item) =>
              [item.embedding_config_name, item.reranker_config_name].filter(Boolean).join(" / ") ||
              "纯词法",
          },
          {
            title: "分数",
            dataIndex: "score",
            width: 100,
            render: (value: number) => value.toFixed(4),
          },
          {
            title: "关联图",
            key: "media",
            width: 90,
            render: (_, item) =>
              (item.media_refs?.length ?? 0) > 0 ? `${item.media_refs.length} 张` : "—",
          },
          {
            title: "降级原因",
            dataIndex: "degradation_reason",
            width: 220,
            ellipsis: true,
            render: (value: string | null) => value ?? "—",
          },
          { title: "内容", dataIndex: "excerpt", ellipsis: true },
        ]}
      />
    </div>
  );
}
