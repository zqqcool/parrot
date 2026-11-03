import { Avatar, Button, Empty, Flex, List, Spin, Tag, Typography } from "antd";

import type { RunDiagnosticTrace } from "@/shared/api/types";
import { AppIcon } from "@/shared/icons";

import { formatRunTime } from "./runDetailModel";
import {
  modelRequestMessageCount,
  modelRequestSnapshot,
  modelRequestToolCount,
  record,
} from "./runDiagnosticTraceModel";
import type { RunEventNodeData } from "./RunEventNode";

type RunPromptListProps = {
  error: unknown;
  loading: boolean;
  traces: RunDiagnosticTrace[];
  onSelect: (node: RunEventNodeData) => void;
};

export function RunPromptList({ error, loading, traces, onSelect }: RunPromptListProps) {
  if (loading) return <Spin className="run-event-loading" />;
  if (error) return <Empty description="模型提示词诊断暂不可用" />;
  const prompts = traces.filter((item) => item.type === "model.request");
  if (!prompts.length) return <Empty description="该运行尚未记录模型提示词" />;
  const messageCount = prompts.reduce(
    (total, trace) => total + modelRequestMessageCount(trace.data),
    0,
  );
  const callsWithTools = prompts.filter((trace) => modelRequestToolCount(trace.data) > 0).length;
  return (
    <section aria-labelledby="run-prompt-list-heading" className="run-prompt-panel">
      <Flex align="flex-start" gap={12} justify="space-between" wrap>
        <div>
          <Typography.Title
            className="run-prompt-panel__title"
            id="run-prompt-list-heading"
            level={3}
          >
            模型调用记录
          </Typography.Title>
          <Typography.Text type="secondary">
            按发生时间展示真实模型请求；可查看完整消息与工具定义。
          </Typography.Text>
        </div>
        <Flex aria-label="模型调用概览" gap={8} wrap>
          <Tag bordered={false}>{prompts.length} 次调用</Tag>
          <Tag bordered={false}>{messageCount} 条消息</Tag>
          <Tag bordered={false}>{callsWithTools} 次携带工具</Tag>
        </Flex>
      </Flex>
      <List
        bordered
        className="run-prompt-list"
        dataSource={prompts}
        itemLayout="horizontal"
        rowKey="id"
        renderItem={(trace) => <PromptListItem key={trace.id} trace={trace} onSelect={onSelect} />}
      />
    </section>
  );
}

function PromptListItem({
  trace,
  onSelect,
}: {
  trace: RunDiagnosticTrace;
  onSelect: RunPromptListProps["onSelect"];
}) {
  const data = trace.data;
  const llm = record(data.llm);
  const snapshot = modelRequestSnapshot(data);
  const phase = text(data.phase) || "agent_loop";
  const actionLabel = snapshot ? "查看请求快照" : "查看请求元数据";
  return (
    <List.Item
      actions={[
        <Button
          aria-label={`${actionLabel}：${phaseLabel(phase)}`}
          icon={<AppIcon name="ArrowRight" size="sm" />}
          iconPosition="end"
          key="view"
          type="link"
          onClick={() => onSelect(node(trace))}
        >
          {actionLabel}
        </Button>,
      ]}
    >
      <List.Item.Meta
        avatar={
          <Avatar
            className="run-prompt-list__avatar"
            icon={<AppIcon name="RobotOne" size="md" />}
            shape="square"
            size={40}
          />
        }
        description={
          <Flex gap={16} wrap>
            <Typography.Text type="secondary">
              {modelRequestMessageCount(data, snapshot)} 条消息
            </Typography.Text>
            <Typography.Text type="secondary">
              {modelRequestToolCount(data, snapshot)} 个工具
            </Typography.Text>
            <Typography.Text type="secondary">诊断 #{trace.sequence}</Typography.Text>
            <Typography.Text type="secondary">
              <time dateTime={trace.occurred_at}>{formatRunTime(trace.occurred_at)}</time>
            </Typography.Text>
          </Flex>
        }
        title={
          <Flex align="center" gap={8} wrap>
            <Tag color="blue">{phaseLabel(phase)}</Tag>
            <Typography.Text className="run-prompt-list__model" strong>
              {text(llm.provider) || "LLM"} / {text(llm.model) || "未记录模型"}
            </Typography.Text>
            <Tag bordered={false} color={snapshot ? "green" : "default"}>
              {snapshot ? "已保存请求快照" : "仅元数据"}
            </Tag>
          </Flex>
        }
      />
    </List.Item>
  );
}

function node(trace: RunDiagnosticTrace): RunEventNodeData {
  return {
    traceId: trace.id,
    eventType: trace.type,
    occurredAt: trace.occurred_at,
    sequence: trace.sequence,
    label: "模型请求",
    detail: modelRequestSnapshot(trace.data)
      ? "查看实际发送给模型的 messages 与工具定义"
      : "仅记录了模型请求元数据",
    state: modelRequestSnapshot(trace.data) ? "请求快照" : "仅元数据",
    icon: "RobotOne",
    tone: "warning",
    diagnosticTrace: trace,
  };
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

const phaseLabels: Record<string, string> = {
  agent_loop: "Agent Loop",
  final_response: "最终回复生成",
  knowledge_intent: "知识意图识别",
  planner: "执行规划",
};

function phaseLabel(phase: string) {
  return phaseLabels[phase] ?? phase;
}
