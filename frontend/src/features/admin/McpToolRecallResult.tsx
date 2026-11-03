import { Empty, List, Space, Tag, Typography } from "antd";

import { CapabilityRecallSummary } from "@/features/admin/CapabilityRecallSummary";
import type { AgentMcpToolRecall } from "@/shared/api/types";

type Candidate = AgentMcpToolRecall["candidates"][number];

export function McpToolRecallResult({ result }: { result: AgentMcpToolRecall }) {
  return (
    <section aria-label="MCP 工具召回结果">
      <CapabilityRecallSummary
        appliedThreshold={result.applied_relevance_threshold}
        candidateCount={result.candidates.length}
        eligibleDescription={`可用 MCP 服务 ${result.eligible_server_count} 个、工具 ${result.eligible_tool_count} 个`}
        retrievalMethod={result.retrieval_method}
      />
      <List
        bordered
        dataSource={result.candidates}
        locale={{
          emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未召回到匹配工具" />,
        }}
        rowKey="id"
        renderItem={(item) => <CandidateItem item={item} />}
      />
    </section>
  );
}

function CandidateItem({ item }: { item: Candidate }) {
  return (
    <List.Item
      extra={
        <Space size="small" wrap>
          {item.relevance_score == null ? null : (
            <Tag>相关度 {item.relevance_score.toFixed(3)}</Tag>
          )}
          <Tag color="blue">第 {item.rank} 位</Tag>
        </Space>
      }
    >
      <List.Item.Meta
        description={item.description || "暂无说明"}
        title={
          <Space size="small" wrap>
            <Typography.Text strong>{item.name}</Typography.Text>
            <Tag>{item.server_name}</Tag>
          </Space>
        }
      />
    </List.Item>
  );
}
