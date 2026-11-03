import { useMemo } from "react";
import { Empty, Spin, Tabs } from "antd";

import type { Run, RunDiagnosticTrace, RunEvent } from "@/shared/api/types";

import { RunEventCanvas } from "./RunEventCanvas";
import type { RunEventNodeData } from "./RunEventNode";
import { RunPromptList } from "./RunPromptList";
import { formatEventPayload, formatRunTime } from "./runDetailModel";

type RunInvestigationProps = {
  diagnosticsError: unknown;
  diagnosticsLoading: boolean;
  events: RunEvent[];
  eventsError: unknown;
  eventsLoading: boolean;
  run: Run;
  selectedEvent?: RunEvent;
  selectedEventId?: string;
  traces: RunDiagnosticTrace[];
  onCanvasSelect: (node: RunEventNodeData) => void;
  onSelectEvent: (eventId: string) => void;
};

export function RunInvestigation({
  diagnosticsError,
  diagnosticsLoading,
  events,
  eventsError,
  eventsLoading,
  run,
  selectedEvent,
  selectedEventId,
  traces,
  onCanvasSelect,
  onSelectEvent,
}: RunInvestigationProps) {
  const promptCount = traces.filter((item) => item.type === "model.request").length;
  const tabs = useMemo(
    () => [
      {
        key: "graph",
        label: "真实运行画布",
        children: (
          <RunEventCanvas
            diagnosticTraces={traces}
            events={events}
            run={run}
            selectedEventId={selectedEventId}
            onSelect={onCanvasSelect}
          />
        ),
      },
      {
        key: "prompts",
        label: `模型提示词 (${promptCount})`,
        children: (
          <RunPromptList
            error={diagnosticsError}
            loading={diagnosticsLoading}
            traces={traces}
            onSelect={onCanvasSelect}
          />
        ),
      },
      {
        key: "timeline",
        label: "事件时间线",
        children: (
          <RunEventTimeline events={events} loading={eventsLoading} onSelect={onSelectEvent} />
        ),
      },
      {
        key: "payload",
        label: "公开事件载荷",
        children: <RunEventPayload event={selectedEvent} />,
      },
    ],
    [
      diagnosticsError,
      diagnosticsLoading,
      events,
      eventsLoading,
      onCanvasSelect,
      onSelectEvent,
      promptCount,
      run,
      selectedEvent,
      selectedEventId,
      traces,
    ],
  );
  return (
    <section className="run-investigation">
      {eventsError ? (
        <Empty description="运行事件暂不可用" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : null}
      <Tabs className="run-investigation-tabs" defaultActiveKey="graph" items={tabs} />
    </section>
  );
}

function RunEventTimeline({
  events,
  loading,
  onSelect,
}: {
  events: RunEvent[];
  loading: boolean;
  onSelect: (eventId: string) => void;
}) {
  if (loading) return <Spin className="run-event-loading" />;
  if (!events.length) return <Empty description="暂无运行事件" />;
  return (
    <ol className="run-event-timeline">
      {events.map((event) => (
        <li key={event.event_id}>
          <button type="button" onClick={() => onSelect(event.event_id)}>
            <span>#{event.sequence}</span>
            <strong>{event.type}</strong>
            <time>{formatRunTime(event.occurred_at)}</time>
          </button>
        </li>
      ))}
    </ol>
  );
}

function RunEventPayload({ event }: { event?: RunEvent }) {
  if (!event) return <Empty description="选择画布中的事件以查看载荷" />;
  return (
    <section className="run-event-payload">
      <header>
        <strong>{event.type}</strong>
        <span>#{event.sequence}</span>
      </header>
      <pre>{formatEventPayload(event.data)}</pre>
    </section>
  );
}
