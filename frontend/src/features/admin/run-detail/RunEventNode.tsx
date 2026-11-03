import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import type { AppIconName } from "@/shared/icons";
import { AppIcon } from "@/shared/icons";
import type { RunDiagnosticTrace } from "@/shared/api/types";

import { formatRunTime } from "./runDetailModel";

export type RunEventNodeData = {
  eventId?: string;
  traceId?: string;
  eventType: string;
  occurredAt: string;
  sequence?: number;
  label: string;
  detail: string;
  state: string;
  icon: AppIconName;
  tone: "default" | "success" | "warning" | "danger";
  modelInput?: {
    entryType: string;
    inputType: string;
    userPrompt: string;
  };
  diagnosticTrace?: RunDiagnosticTrace;
};

export type RunEventFlowNode = Node<RunEventNodeData, "runEvent">;

export function RunEventNode({ data }: NodeProps<RunEventFlowNode>) {
  return (
    <article className={`run-event-node run-event-node--${data.tone}`}>
      <Handle className="run-event-node__handle" position={Position.Left} type="target" />
      <header>
        <span className="run-event-node__identity">
          <span className="run-event-node__icon">
            <AppIcon name={data.icon} size="sm" theme="filled" />
          </span>
          <span>{data.label}</span>
        </span>
        {data.sequence ? <span className="run-event-node__sequence">#{data.sequence}</span> : null}
      </header>
      <strong className="run-event-node__type">{data.eventType}</strong>
      <p className="run-event-node__detail">{data.detail}</p>
      <footer>
        <span className="run-event-node__time">
          <AppIcon name="History" size="sm" />
          {formatRunTime(data.occurredAt)}
        </span>
        <span className="run-event-node__state">{data.state}</span>
      </footer>
      <Handle className="run-event-node__handle" position={Position.Right} type="source" />
    </article>
  );
}
