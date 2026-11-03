import { useState } from "react";
import { Descriptions, Tag } from "antd";

import type { Run, RunDiagnosticTrace, RunEvent } from "@/shared/api/types";
import type { RunTaskBoard as RunTaskBoardType } from "@/shared/api/types";

import { RunEventDrawer } from "./RunEventDrawer";
import { RunInvestigation } from "./RunInvestigation";
import { RunTaskBoard } from "./RunTaskBoard";
import type { RunEventNodeData } from "./RunEventNode";
import {
  formatRunTime,
  getRunMetrics,
  getRunOutput,
  socketStateLabel,
  statusColor,
} from "./runDetailModel";

import "./run-detail.css";
import "./run-event-drawer.css";
import "./run-event-details.css";

type RunDetailContentProps = {
  events: RunEvent[];
  eventsError: unknown;
  eventsLoading: boolean;
  diagnosticTraces: RunDiagnosticTrace[];
  diagnosticsError: unknown;
  diagnosticsLoading: boolean;
  run: Run;
  socketState: string;
  taskBoard: RunTaskBoardType | undefined;
  taskBoardError: unknown;
  taskBoardLoading: boolean;
};

export function RunDetailContent({
  events,
  eventsError,
  eventsLoading,
  diagnosticTraces,
  diagnosticsError,
  diagnosticsLoading,
  run,
  socketState,
  taskBoard,
  taskBoardError,
  taskBoardLoading,
}: RunDetailContentProps) {
  const [selectedEventId, setSelectedEventId] = useState<string>();
  const [drawerNode, setDrawerNode] = useState<RunEventNodeData>();
  const output = getRunOutput(events);
  const selectedEvent =
    events.find((event) => event.event_id === selectedEventId) ?? events[events.length - 1];
  const drawerEvent = events.find((event) => event.event_id === drawerNode?.eventId);
  const metrics = getRunMetrics(run, events);
  const selectCanvasNode = (node: RunEventNodeData) => {
    if (node.eventId) setSelectedEventId(node.eventId);
    setDrawerNode(node);
  };

  return (
    <div className="run-detail-content">
      <RunOverview run={run} socketState={socketState} />
      <section className="run-task-board-section">
        <h2>任务拆解</h2>
        <RunTaskBoard error={taskBoardError} loading={taskBoardLoading} taskBoard={taskBoard} />
      </section>
      <section className="run-detail-io-grid">
        <RunTextPanel label="输入" value={run.input_summary || "未记录文本输入"} />
        <RunTextPanel label="结果" value={output || "等待模型输出…"} muted={!output} />
      </section>
      <section className="run-metric-grid" aria-label="运行指标">
        {metrics.map((metric) => (
          <div className="run-metric" key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </section>
      <RunInvestigation
        diagnosticsError={diagnosticsError}
        diagnosticsLoading={diagnosticsLoading}
        eventsError={eventsError}
        events={events}
        eventsLoading={eventsLoading}
        run={run}
        selectedEvent={selectedEvent}
        selectedEventId={selectedEventId}
        onCanvasSelect={selectCanvasNode}
        traces={diagnosticTraces}
        onSelectEvent={setSelectedEventId}
      />
      <RunEventDrawer
        event={drawerEvent}
        node={drawerNode}
        open={Boolean(drawerNode)}
        onClose={() => setDrawerNode(undefined)}
      />
    </div>
  );
}

function RunOverview({ run, socketState }: { run: Run; socketState: string }) {
  return (
    <Descriptions
      bordered
      className="run-overview"
      column={{ xl: 4, lg: 3, md: 2, sm: 1, xs: 1 }}
      items={[
        { key: "id", label: "Run ID", children: run.id },
        {
          key: "status",
          label: "状态",
          children: <Tag color={statusColor(run.status)}>{run.status}</Tag>,
        },
        { key: "agent", label: "智能体", children: run.agent_name },
        { key: "entry", label: "入口", children: run.entry_type },
        { key: "input", label: "输入类型", children: run.input_type },
        { key: "runtime", label: "运行时 ID", children: run.runtime_execution_id ?? "-" },
        { key: "created", label: "创建于", children: formatRunTime(run.created_at) },
        { key: "updated", label: "更新于", children: formatRunTime(run.updated_at) },
        { key: "stream", label: "实时通道", children: socketStateLabel(socketState) },
      ]}
      size="small"
    />
  );
}

function RunTextPanel({
  label,
  muted = false,
  value,
}: {
  label: string;
  muted?: boolean;
  value: string;
}) {
  return (
    <section className="run-text-panel">
      <h2>{label}</h2>
      <pre className={muted ? "run-text-panel__empty" : undefined}>{value}</pre>
    </section>
  );
}
