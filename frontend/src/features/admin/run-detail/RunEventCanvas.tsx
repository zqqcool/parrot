import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  type NodeMouseHandler,
} from "@xyflow/react";
import { Empty } from "antd";

import type { Run, RunDiagnosticTrace, RunEvent } from "@/shared/api/types";

import { RunEventNode, type RunEventFlowNode, type RunEventNodeData } from "./RunEventNode";
import { createRunTraceGraph } from "./runTraceGraph";

import "@xyflow/react/dist/style.css";

const nodeTypes = { runEvent: RunEventNode };

type RunEventCanvasProps = {
  run: Run;
  events: RunEvent[];
  diagnosticTraces: RunDiagnosticTrace[];
  selectedEventId?: string;
  onSelect: (node: RunEventNodeData) => void;
};

export function RunEventCanvas({
  run,
  events,
  diagnosticTraces,
  selectedEventId,
  onSelect,
}: RunEventCanvasProps) {
  if (!events.length) {
    return <Empty className="run-event-canvas-empty" description="暂无可绘制的运行事件" />;
  }
  return (
    <ReactFlowProvider>
      <RunEventCanvasContent
        run={run}
        events={events}
        diagnosticTraces={diagnosticTraces}
        onSelect={onSelect}
        selectedEventId={selectedEventId}
      />
    </ReactFlowProvider>
  );
}

function RunEventCanvasContent({
  run,
  events,
  diagnosticTraces,
  selectedEventId,
  onSelect,
}: RunEventCanvasProps) {
  const graph = useMemo(
    () => createRunTraceGraph(run, events, diagnosticTraces, selectedEventId),
    [diagnosticTraces, events, run, selectedEventId],
  );
  const selectNode: NodeMouseHandler<RunEventFlowNode> = (_event, node) => {
    onSelect(node.data);
  };
  const outputDeltas = events.filter((event) => event.type === "ai.output.delta").length;

  return (
    <div className="run-event-canvas" aria-label="运行事件画布">
      <ReactFlow<RunEventFlowNode>
        edges={graph.edges}
        fitView
        fitViewOptions={{ padding: 0.28, maxZoom: 1, minZoom: 0.1 }}
        maxZoom={1.5}
        minZoom={0.1}
        nodes={graph.nodes}
        nodeTypes={nodeTypes}
        nodesConnectable={false}
        nodesDraggable={false}
        onNodeClick={selectNode}
        panOnDrag
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#cbdcf2" gap={18} size={1} variant={BackgroundVariant.Dots} />
        <Panel className="run-event-canvas__title" position="top-left">
          <span className="run-event-canvas__eyebrow">EXECUTION TRACE</span>
          <strong>运行轨迹</strong>
          <span>聚合入口、Agent Loop、输入、输出与状态</span>
        </Panel>
        <Panel className="run-event-canvas__stats" position="top-right">
          <span>
            <strong>{graph.nodes.length}</strong>
            关键节点
          </span>
          <span>
            <strong>{outputDeltas}</strong>
            流式片段
          </span>
          <span>
            <strong>{diagnosticTraces.length}</strong>
            诊断记录
          </span>
          <span className="run-event-canvas__terminal">{run.status}</span>
        </Panel>
        <Controls showInteractive={false} />
        <MiniMap maskColor="rgba(255, 255, 255, 0.65)" pannable zoomable />
      </ReactFlow>
    </div>
  );
}
