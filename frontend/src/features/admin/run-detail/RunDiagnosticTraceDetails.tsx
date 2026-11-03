import type { ReactNode } from "react";
import { Collapse, Descriptions, Empty, Tag } from "antd";

import type { RunDiagnosticTrace } from "@/shared/api/types";

import { formatEventPayload, formatRunTime } from "./runDetailModel";
import {
  modelRequestMessageCount,
  modelRequestSnapshot,
  modelRequestToolCount,
  record,
} from "./runDiagnosticTraceModel";

type RunDiagnosticTraceDetailsProps = { trace: RunDiagnosticTrace };

export function RunDiagnosticTraceDetails({ trace }: RunDiagnosticTraceDetailsProps) {
  if (trace.type === "model.request") return <ModelRequestDetails trace={trace} />;
  if (trace.type === "tool.call") return <ToolCallDetails trace={trace} />;
  if (trace.type === "tool.result") return <ToolResultDetails trace={trace} />;
  return <Empty description="不支持的诊断记录" />;
}

function ModelRequestDetails({ trace }: RunDiagnosticTraceDetailsProps) {
  const llm = record(trace.data.llm);
  const snapshot = modelRequestSnapshot(trace.data);
  const messages = snapshot?.messages ?? [];
  const tools = snapshot?.tools ?? [];
  return (
    <DiagnosticLayout trace={trace} summary="模型请求快照">
      <Descriptions
        bordered
        column={1}
        items={[
          { key: "phase", label: "运行阶段", children: text(trace.data.phase) || "agent_loop" },
          {
            key: "model",
            label: "模型",
            children: `${text(llm.provider) || "LLM"} / ${text(llm.model) || "未记录"}`,
          },
          { key: "attempt", label: "调用尝试", children: text(trace.data.attempt) || "1" },
          {
            key: "messages",
            label: "Messages",
            children: `${modelRequestMessageCount(trace.data, snapshot)} 条`,
          },
          {
            key: "tools",
            label: "Tools",
            children: `${modelRequestToolCount(trace.data, snapshot)} 个`,
          },
        ]}
        size="small"
      />
      {snapshot ? (
        <>
          <TraceCollapse label="实际发送给模型的 messages" values={messages} valueKey="content" />
          <TraceCollapse label="实际发送给模型的工具定义" values={tools} />
        </>
      ) : (
        <Empty description="该运行未保存完整请求快照" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
    </DiagnosticLayout>
  );
}

function ToolCallDetails({ trace }: RunDiagnosticTraceDetailsProps) {
  return (
    <DiagnosticLayout trace={trace} summary="工具调用参数">
      <Descriptions
        bordered
        column={1}
        items={[
          { key: "name", label: "工具", children: text(trace.data.name) || "未命名工具" },
          { key: "id", label: "调用 ID", children: text(trace.data.tool_call_id) || "-" },
          { key: "arguments", label: "参数数量", children: text(trace.data.argument_count) || "0" },
        ]}
        size="small"
      />
    </DiagnosticLayout>
  );
}

function ToolResultDetails({ trace }: RunDiagnosticTraceDetailsProps) {
  return (
    <DiagnosticLayout trace={trace} summary="工具执行结果">
      <Descriptions
        bordered
        column={1}
        items={[
          { key: "name", label: "工具", children: text(trace.data.name) || "未命名工具" },
          { key: "id", label: "调用 ID", children: text(trace.data.tool_call_id) || "-" },
          {
            key: "status",
            label: "执行状态",
            children: <Tag>{text(trace.data.status) || "未记录"}</Tag>,
          },
          { key: "code", label: "结果代码", children: text(trace.data.code) || "-" },
        ]}
        size="small"
      />
    </DiagnosticLayout>
  );
}

function DiagnosticLayout({
  children,
  summary,
  trace,
}: RunDiagnosticTraceDetailsProps & { children: ReactNode; summary: string }) {
  return (
    <div className="run-event-drawer__content">
      <section className="run-event-drawer__summary">
        <span>{summary}</span>
        <strong>{trace.type}</strong>
      </section>
      <Descriptions
        bordered
        column={1}
        items={[
          { key: "sequence", label: "诊断序号", children: `#${trace.sequence}` },
          { key: "time", label: "发生时间", children: formatRunTime(trace.occurred_at) },
        ]}
        size="small"
      />
      {children}
    </div>
  );
}

function TraceCollapse({
  label,
  values,
  valueKey,
}: {
  label: string;
  values: Record<string, unknown>[];
  valueKey?: string;
}) {
  if (!values.length)
    return <Empty description={`${label}为空`} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  return (
    <section className="run-diagnostic-section">
      <h3>{label}</h3>
      <Collapse
        items={values.map((value, index) => ({
          key: String(index),
          label: collapseLabel(value, index),
          children: (
            <TracePayload label="内容" value={valueKey ? (value[valueKey] ?? value) : value} />
          ),
        }))}
      />
    </section>
  );
}

function TracePayload({ label, value }: { label: string; value: unknown }) {
  return (
    <section className="run-event-drawer__payload" aria-label={label}>
      <header>
        <span>{label}</span>
        <span>{typeof value === "string" ? "TEXT" : "JSON"}</span>
      </header>
      <pre>{typeof value === "string" ? value : formatEventPayload(record(value))}</pre>
    </section>
  );
}

function collapseLabel(value: Record<string, unknown>, index: number) {
  const role = text(value.role);
  const name = text(value.name);
  return [role || name || `项目 ${index + 1}`, text(value.tool_call_id)]
    .filter(Boolean)
    .join(" · ");
}

function text(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}
