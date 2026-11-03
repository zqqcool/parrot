import { Descriptions, Drawer, Empty, Tag } from "antd";

import type { RunEvent } from "@/shared/api/types";

import { RunDiagnosticTraceDetails } from "./RunDiagnosticTraceDetails";
import { formatEventPayload, formatRunTime } from "./runDetailModel";
import type { RunEventNodeData } from "./RunEventNode";

type RunEventDrawerProps = {
  event?: RunEvent;
  node?: RunEventNodeData;
  open: boolean;
  onClose: () => void;
};

export function RunEventDrawer({ event, node, open, onClose }: RunEventDrawerProps) {
  return (
    <Drawer
      className="run-event-drawer"
      closable={{ "aria-label": "关闭事件详情" }}
      destroyOnHidden
      extra={<DrawerExtra event={event} node={node} />}
      open={open}
      placement="right"
      title={drawerTitle(node)}
      width="min(560px, 100vw)"
      onClose={onClose}
    >
      <DrawerContent event={event} node={node} />
    </Drawer>
  );
}

function DrawerExtra({ event, node }: Pick<RunEventDrawerProps, "event" | "node">) {
  const sequence = node?.sequence ?? event?.sequence;
  return sequence ? <Tag color="blue">#{sequence}</Tag> : null;
}

const diagnosticTitles: Record<string, string> = {
  "model.request": "模型提示词详情",
  "tool.call": "工具调用详情",
  "tool.result": "工具结果详情",
};

function drawerTitle(node?: RunEventNodeData) {
  const title = node?.diagnosticTrace ? diagnosticTitles[node.diagnosticTrace.type] : undefined;
  if (title) return title;
  return node?.modelInput ? "用户提示词详情" : "事件详情";
}

function DrawerContent({ event, node }: Pick<RunEventDrawerProps, "event" | "node">) {
  if (node?.diagnosticTrace) return <RunDiagnosticTraceDetails trace={node.diagnosticTrace} />;
  if (node?.modelInput) return <ModelInputDetails event={event} node={node} />;
  if (event) return <RunEventDetails event={event} />;
  return <Empty description="事件已不在当前运行记录中" />;
}

function ModelInputDetails({ event, node }: { event?: RunEvent; node: RunEventNodeData }) {
  const input = node.modelInput;
  if (!input) return null;
  return (
    <div className="run-event-drawer__content">
      <section className="run-event-drawer__summary">
        <span>提交给模型的用户输入</span>
        <strong>{node.eventType}</strong>
      </section>
      <Descriptions
        bordered
        column={1}
        items={[
          { key: "entry", label: "入口", children: input.entryType },
          { key: "input-type", label: "输入类型", children: input.inputType },
          { key: "event", label: "关联事件", children: event ? `#${event.sequence}` : "未持久化" },
          { key: "time", label: "发生时间", children: formatRunTime(node.occurredAt) },
        ]}
        size="small"
      />
      <section className="run-event-drawer__payload" aria-label="提交给模型的用户输入">
        <header>
          <span>提交给模型的用户输入</span>
          <span>TEXT</span>
        </header>
        <pre>{input.userPrompt}</pre>
      </section>
      {event ? <RunEventPayload event={event} /> : null}
    </div>
  );
}

function RunEventDetails({ event }: { event: RunEvent }) {
  return (
    <div className="run-event-drawer__content">
      <section className="run-event-drawer__summary">
        <span>事件类型</span>
        <strong>{event.type}</strong>
      </section>
      <Descriptions
        bordered
        column={1}
        items={[
          { key: "sequence", label: "事件序号", children: `#${event.sequence}` },
          { key: "occurred-at", label: "发生时间", children: formatRunTime(event.occurred_at) },
          { key: "event-id", label: "事件 ID", children: event.event_id },
          { key: "request-id", label: "请求 ID", children: event.request_id || "-" },
        ]}
        size="small"
      />
      <RunEventPayload event={event} />
    </div>
  );
}

function RunEventPayload({ event }: { event: RunEvent }) {
  return (
    <section className="run-event-drawer__payload" aria-label="事件载荷">
      <header>
        <span>事件载荷</span>
        <span>JSON</span>
      </header>
      <pre>{formatEventPayload(event.data)}</pre>
    </section>
  );
}
