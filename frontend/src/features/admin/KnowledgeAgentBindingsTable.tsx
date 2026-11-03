import { Button, Popconfirm, Space, Table, Tag, Typography } from "antd";

import type { AdminAgent } from "@/shared/api/types";

type Props = {
  agents: AdminAgent[];
  loading: boolean;
  unbinding: boolean;
  unbindingAgentId: string | undefined;
  onUnbind: (agentId: string) => void;
};

function AgentStatus({ agent }: { agent: AdminAgent }) {
  if (agent.status !== "active") return <Tag>已停用</Tag>;
  if (!agent.published) return <Tag color="warning">未发布</Tag>;
  return <Tag color="success">启用</Tag>;
}

export function KnowledgeAgentBindingsTable({
  agents,
  loading,
  unbinding,
  unbindingAgentId,
  onUnbind,
}: Props) {
  return (
    <Table<AdminAgent>
      dataSource={agents}
      loading={loading}
      locale={{ emptyText: "当前知识库尚未关联 Agent" }}
      pagination={false}
      rowKey="id"
      size="small"
      columns={[
        {
          title: "Agent",
          render: (_, agent) => (
            <div>
              <div>{agent.name}</div>
              <Typography.Text type="secondary">{agent.slug}</Typography.Text>
            </div>
          ),
        },
        {
          title: "状态",
          width: 180,
          render: (_, agent) => (
            <Space size={4} wrap>
              <AgentStatus agent={agent} />
              {agent.allow_anonymous ? <Tag color="orange">允许匿名</Tag> : null}
            </Space>
          ),
        },
        {
          title: "操作",
          width: 110,
          render: (_, agent) => (
            <Popconfirm
              title={`解除与 ${agent.name} 的关联？`}
              description="解除后，该 Agent 将不能再检索当前知识库。"
              okText="解除关联"
              cancelText="取消"
              onConfirm={() => onUnbind(agent.id)}
            >
              <Button
                danger
                size="small"
                type="link"
                disabled={unbinding && unbindingAgentId !== agent.id}
                loading={unbinding && unbindingAgentId === agent.id}
              >
                解除关联
              </Button>
            </Popconfirm>
          ),
        },
      ]}
    />
  );
}
