import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Drawer, Form, Select, Space, Tag } from "antd";

import { ScheduleModal } from "@/features/admin/ScheduleModal";
import {
  type ScheduleForm,
  scheduleToForm,
  toScheduleCreate,
  toScheduleUpdate,
} from "@/features/admin/scheduleForm";
import { useTenantId } from "@/features/admin/useTenant";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { adminApi } from "@/shared/api/client";
import type { Schedule, SessionData } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { formatDateTime } from "@/shared/time";
import {
  AdminPageHeader,
  CreateButton,
  DataTable,
  SearchBar,
  useDebouncedValue,
  UserIdentity,
} from "@/shared/ui";

export function SchedulesPage() {
  const tenantId = useTenantId();
  const auth = useAuth();
  const client = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Schedule | null>(null);
  const [selected, setSelected] = useState<Schedule | null>(null);
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const [statusFilter, setStatusFilter] = useState<"all" | "enabled" | "disabled">("all");
  const [form] = Form.useForm<ScheduleForm>();
  const canManage = auth.hasPermission("schedules.manage");
  const defaultTimezone = scheduleDefaultTimezone(auth.session);
  const query = useQuery({
    queryKey: ["admin", tenantId, "schedules", searchQuery],
    queryFn: () => adminApi.listSchedules(tenantId ?? "", searchQuery),
    enabled: Boolean(tenantId),
  });
  const agents = useQuery({
    queryKey: ["admin", tenantId, "agents"],
    queryFn: () => adminApi.listAgents(tenantId ?? ""),
    enabled: Boolean(tenantId),
  });
  const executions = useQuery({
    queryKey: ["admin", tenantId, "schedules", selected?.id, "executions"],
    queryFn: () => adminApi.listScheduleExecutions(tenantId ?? "", selected?.id ?? ""),
    enabled: Boolean(selected),
    refetchInterval: 3_000,
  });
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", tenantId, "schedules"] });
  const create = useMutation({
    mutationFn: (values: ScheduleForm) =>
      adminApi.createSchedule(tenantId ?? "", toScheduleCreate(values)),
    onSuccess: async () => {
      setCreating(false);
      form.resetFields();
      await refresh();
    },
  });
  const update = useMutation({
    mutationFn: (values: ScheduleForm) =>
      adminApi.updateSchedule(tenantId ?? "", editing?.id ?? "", toScheduleUpdate(values)),
    onSuccess: async () => {
      setEditing(null);
      form.resetFields();
      await refresh();
    },
  });
  const toggle = useMutation({
    mutationFn: (item: Schedule) =>
      adminApi.setScheduleEnabled(tenantId ?? "", item.id, item.status !== "enabled"),
    onSuccess: refresh,
  });
  const runNow = useMutation({
    mutationFn: (item: Schedule) => adminApi.runScheduleNow(tenantId ?? "", item.id),
    onSuccess: async (_, item) => {
      setSelected(item);
      await client.invalidateQueries({
        queryKey: ["admin", tenantId, "schedules", item.id, "executions"],
      });
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "runs"] });
    },
  });
  if (!tenantId) return <TenantRequiredState />;
  const schedules = filterSchedules(query.data, statusFilter);
  return (
    <section>
      <AdminPageHeader
        title="定时任务"
        description="配置 Cron 或单次任务；调度进程触发后复用统一 Agent 运行链路，可在运行进度中实时追踪。"
      />
      <SearchBar
        actions={
          <ScheduleCreateAction
            canManage={canManage}
            onClick={() => {
              form.resetFields();
              form.setFieldsValue({ schedule_type: "recurring", timezone: defaultTimezone });
              setCreating(true);
            }}
          />
        }
        advancedFilters={
          <Select
            aria-label="按状态筛选定时任务"
            options={[
              { value: "all", label: "全部状态" },
              { value: "enabled", label: "启用" },
              { value: "disabled", label: "停用" },
            ]}
            value={statusFilter}
            onChange={setStatusFilter}
          />
        }
        hasActiveFilters={statusFilter !== "all"}
        placeholder="搜索任务名称、类型或 Cron 表达式"
        value={searchValue}
        onChange={setSearchValue}
        onReset={() => {
          setSearchValue("");
          setStatusFilter("all");
        }}
      />
      <DataTable
        rowKey="id"
        loading={query.isFetching}
        dataSource={schedules}
        resetPaginationKey={`${searchQuery}:${statusFilter}`}
        columns={[
          { title: "任务名称", dataIndex: "title" },
          {
            title: "创建人",
            dataIndex: "creator",
            width: 150,
            render: (_value, item) => <UserIdentity tenantId={tenantId} user={item.creator} />,
          },
          { title: "类型", dataIndex: "schedule_type", width: 100 },
          {
            title: "计划",
            key: "timing",
            render: (_, item) => item.cron_expr ?? formatDateTime(item.run_at),
          },
          { title: "时区", dataIndex: "timezone", width: 130 },
          { title: "下次触发", dataIndex: "next_trigger_at", width: 180, render: formatDateTime },
          { title: "状态", dataIndex: "status", width: 100, render: scheduleStatus },
          {
            title: "操作",
            width: 220,
            render: (_, item) => (
              <Space>
                <Button type="link" size="small" onClick={() => setSelected(item)}>
                  执行记录
                </Button>
                {canManage ? (
                  <Button
                    type="link"
                    size="small"
                    onClick={() => {
                      form.setFieldsValue(scheduleToForm(item));
                      setEditing(item);
                    }}
                  >
                    编辑
                  </Button>
                ) : null}
                {canManage ? (
                  <Button
                    type="link"
                    size="small"
                    loading={runNow.isPending && runNow.variables?.id === item.id}
                    onClick={() => runNow.mutate(item)}
                  >
                    立即执行
                  </Button>
                ) : null}
                {canManage ? (
                  <Button type="link" size="small" onClick={() => toggle.mutate(item)}>
                    {item.status === "enabled" ? "停用" : "启用"}
                  </Button>
                ) : null}
              </Space>
            ),
          },
        ]}
      />
      <ScheduleModal
        open={creating || Boolean(editing)}
        form={form}
        agents={publishedAgentOptions(agents.data)}
        loading={create.isPending || update.isPending}
        error={editing ? update.error : create.error}
        agentDisabled={Boolean(editing)}
        defaultTimezone={defaultTimezone}
        title={editing ? "编辑定时任务" : "新建定时任务"}
        errorFallback={editing ? "更新定时任务失败" : "创建定时任务失败"}
        onCancel={() => {
          setCreating(false);
          setEditing(null);
        }}
        onSubmit={(values) => {
          if (editing) update.mutate(values);
          else create.mutate(values);
        }}
      />
      <Drawer
        title={`执行记录 · ${selected?.title ?? ""}`}
        width={620}
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
      >
        <DataTable
          rowKey="id"
          loading={executions.isPending}
          dataSource={executions.data}
          columns={[
            { title: "触发时间", dataIndex: "scheduled_for", render: formatDateTime },
            { title: "触发方式", dataIndex: "trigger_type", width: 90 },
            { title: "状态", dataIndex: "status", width: 100, render: scheduleStatus },
            { title: "Run ID", dataIndex: "interaction_id", ellipsis: true },
          ]}
        />
      </Drawer>
    </section>
  );
}

function ScheduleCreateAction({ canManage, onClick }: { canManage: boolean; onClick: () => void }) {
  return canManage ? <CreateButton onClick={onClick} /> : null;
}

function publishedAgentOptions(items: Awaited<ReturnType<typeof adminApi.listAgents>> | undefined) {
  return (
    items?.filter((item) => item.published).map((item) => ({ label: item.name, value: item.id })) ??
    []
  );
}

function scheduleStatus(value: string) {
  return (
    <Tag
      color={
        value === "enabled" || value === "completed"
          ? "success"
          : value === "failed"
            ? "error"
            : "default"
      }
    >
      {value}
    </Tag>
  );
}
function filterSchedules(
  schedules: Schedule[] | undefined,
  statusFilter: "all" | "enabled" | "disabled",
) {
  return (schedules ?? []).filter((item) => statusFilter === "all" || item.status === statusFilter);
}

function scheduleDefaultTimezone(session: SessionData | null): string | undefined {
  return session?.default_schedule_timezone;
}
