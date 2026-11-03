import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { Button, Drawer, Result, Spin } from "antd";

import { InteractionSocket } from "@/features/ai-chat/transport/InteractionSocket";
import { RunDetailContent } from "@/features/admin/run-detail/RunDetailContent";
import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import type { ImEnvelope } from "@/shared/api/generated/im";
import type { Run, RunEvent } from "@/shared/api/types";
import { AppIcon } from "@/shared/icons";

const terminalStatuses = new Set(["completed", "failed", "cancelled", "partial"]);

type RunDetailDrawerProps = {
  runId: string;
  onClose: () => void;
};

export function RunDetailDrawer({ runId, onClose }: RunDetailDrawerProps) {
  const tenantId = useTenantId();
  const [refreshing, setRefreshing] = useState(false);
  const runQuery = useQuery({
    queryKey: ["admin", tenantId, "runs", runId],
    queryFn: () => adminApi.getRun(tenantId ?? "", runId),
    enabled: Boolean(tenantId && runId),
  });
  const taskBoardQuery = useQuery({
    queryKey: ["admin", tenantId, "runs", runId, "task-board"],
    queryFn: () => adminApi.getRunTaskBoard(tenantId ?? "", runId),
    enabled: Boolean(tenantId && runId && runQuery.data),
  });
  const diagnosticsQuery = useQuery({
    queryKey: ["admin", tenantId, "runs", runId, "diagnostic-traces"],
    queryFn: () => adminApi.listRunDiagnosticTraces(tenantId ?? "", runId),
    enabled: Boolean(tenantId && runId && runQuery.data),
    refetchInterval: terminalStatuses.has(runQuery.data?.status ?? "") ? false : 1_500,
  });
  const live = useRunLiveEvents(tenantId, runId, runQuery.data);
  const refresh = async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        runQuery.refetch(),
        taskBoardQuery.refetch(),
        diagnosticsQuery.refetch(),
        live.eventsQuery.refetch(),
      ]);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <Drawer
      className="run-detail-drawer"
      closable={{ "aria-label": "关闭 Run 详情" }}
      destroyOnHidden
      extra={
        <Button
          aria-label="刷新 Run 详情"
          disabled={[runQuery.isPending, refreshing].includes(true)}
          icon={<AppIcon name="Refresh" size="sm" />}
          loading={refreshing}
          onClick={() => void refresh()}
        >
          刷新
        </Button>
      }
      open
      placement="right"
      title="Run 详情"
      width="100vw"
      onClose={onClose}
    >
      <Spin spinning={Boolean(refreshing)} tip="正在刷新 Run 详情">
        <div aria-busy={refreshing}>
          <RunDetailDrawerBody
            events={live.events}
            eventsError={live.eventsQuery.error}
            eventsLoading={live.eventsQuery.isPending}
            diagnosticTraces={diagnosticsQuery.data ?? []}
            diagnosticsError={diagnosticsQuery.error}
            diagnosticsLoading={diagnosticsQuery.isPending}
            run={runQuery.data}
            runError={runQuery.error}
            runLoading={runQuery.isPending}
            socketState={live.socketState}
            taskBoard={taskBoardQuery.data}
            taskBoardError={taskBoardQuery.error}
            taskBoardLoading={taskBoardQuery.isPending}
          />
        </div>
      </Spin>
    </Drawer>
  );
}

function RunDetailDrawerBody({
  diagnosticTraces,
  diagnosticsError,
  diagnosticsLoading,
  events,
  eventsError,
  eventsLoading,
  run,
  runError,
  runLoading,
  socketState,
  taskBoard,
  taskBoardError,
  taskBoardLoading,
}: {
  diagnosticTraces: Awaited<ReturnType<typeof adminApi.listRunDiagnosticTraces>>;
  diagnosticsError: unknown;
  diagnosticsLoading: boolean;
  events: RunEvent[];
  eventsError: unknown;
  eventsLoading: boolean;
  run: Run | undefined;
  runError: unknown;
  runLoading: boolean;
  socketState: string;
  taskBoard: Awaited<ReturnType<typeof adminApi.getRunTaskBoard>> | undefined;
  taskBoardError: unknown;
  taskBoardLoading: boolean;
}) {
  if (runLoading) return <Result status="info" title="正在加载 Run" />;
  if (runError) return <Result status="error" title="Run 详情暂不可用" />;
  if (!run) return <Result status="404" title="Run 不存在或无权查看" />;

  return (
    <RunDetailContent
      diagnosticTraces={diagnosticTraces}
      diagnosticsError={diagnosticsError}
      diagnosticsLoading={diagnosticsLoading}
      events={events}
      eventsError={eventsError}
      eventsLoading={eventsLoading}
      run={run}
      socketState={socketState}
      taskBoard={taskBoard}
      taskBoardError={taskBoardError}
      taskBoardLoading={taskBoardLoading}
    />
  );
}

function useRunLiveEvents(tenantId: string | null, runId: string, run: Run | undefined) {
  const client = useQueryClient();
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [socketState, setSocketState] = useState("disconnected");
  const eventsQuery = useQuery({
    queryKey: ["admin", tenantId, "runs", runId, "events"],
    queryFn: () => adminApi.listRunEvents(tenantId ?? "", runId),
    enabled: Boolean(tenantId && run),
  });

  useEffect(() => setEvents(eventsQuery.data ?? []), [eventsQuery.data]);
  useEffect(() => {
    if (!run || terminalStatuses.has(run.status)) return;
    setSocketState("connecting");
    const socket = new InteractionSocket({
      interactionId: run.id,
      afterSequence: 0,
      admin: true,
      onState: setSocketState,
      onEvent: (event) => handleSocketEvent(event, setEvents, client, tenantId),
    });
    socket.connect();
    return () => socket.close();
  }, [client, run, tenantId]);

  return { events, eventsQuery, socketState };
}

function handleSocketEvent(
  event: ImEnvelope,
  setEvents: Dispatch<SetStateAction<RunEvent[]>>,
  client: QueryClient,
  tenantId: string | null,
) {
  const runEvent = envelopeToRunEvent(event);
  if (!runEvent) return;
  setEvents((current) => mergeEvents(current, runEvent));
  if (event.type.startsWith("ai.")) {
    void client.invalidateQueries({ queryKey: ["admin", tenantId, "runs"] });
  }
}

function envelopeToRunEvent(event: ImEnvelope): RunEvent | null {
  if (!event.sequence || !event.occurred_at) return null;
  return {
    type: event.type,
    event_id: event.message_id,
    request_id: event.request_id,
    occurred_at: event.occurred_at,
    sequence: event.sequence,
    data: event.data,
  };
}

function mergeEvents(current: RunEvent[], event: RunEvent) {
  return current.some((item) => item.event_id === event.event_id) ? current : [...current, event];
}
