import { Empty, List, Space, Tag } from "antd";
import { Link } from "react-router-dom";

import { CapabilityRecallSummary } from "@/features/admin/CapabilityRecallSummary";
import type { AgentSkillRecall } from "@/shared/api/types";

type Candidate = AgentSkillRecall["candidates"][number];

export function SkillRecallResult({ result }: { result: AgentSkillRecall }) {
  return (
    <section aria-label="Skill 召回结果">
      <CapabilityRecallSummary
        appliedThreshold={result.applied_relevance_threshold}
        candidateCount={result.candidates.length}
        eligibleDescription={`可用 Skill ${result.eligible_skill_count} 个`}
        retrievalMethod={result.retrieval_method}
      />
      <List
        bordered
        dataSource={result.candidates}
        locale={{
          emptyText: (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未召回到匹配 Skill" />
          ),
        }}
        rowKey="id"
        renderItem={(item) => <CandidateItem item={item} />}
      />
    </section>
  );
}

function CandidateItem({ item }: { item: Candidate }) {
  const score = item.relevance_score;
  return (
    <List.Item
      extra={
        <Space size="small" wrap>
          {score == null ? null : <Tag>相关度 {score.toFixed(3)}</Tag>}
          <Tag color="blue">第 {item.rank} 位</Tag>
        </Space>
      }
    >
      <List.Item.Meta
        description={item.description || "暂无说明"}
        title={
          <Space size="small" wrap>
            <Link to={`/admin/skills/${item.id}`}>{item.name}</Link>
            <Tag>v{item.version}</Tag>
          </Space>
        }
      />
    </List.Item>
  );
}
