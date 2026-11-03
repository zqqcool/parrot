import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Form, Space, Tag } from "antd";
import { Link } from "react-router-dom";

import { ScheduleModal } from "@/features/admin/ScheduleModal";
import { type ScheduleForm, toScheduleCreate } from "@/features/admin/scheduleForm";
import { adminApi } from "@/shared/api/client";
import type { AdminAgent as Agent, Schedule } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { formatDateTime } from "@/shared/time";
import { DataTable, RequestErrorAlert } from "@/shared/ui";

type Props = {
  agent: Agent;
  canManage: boolean;
  tenantId: string;
};

export function AgentSchedulesSection({ agent, canManage, tenantId }: Props) {
  const auth = useAuth();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<ScheduleForm>();
  const schedules = useQuery({
    queryKey: ["admin", tenantId, "schedules"],
    queryFn: () => adminApi.listSchedules(tenantId),
  });
  const create = useMutation({
    mutationFn: (values: ScheduleForm) =>
      adminApi.createSchedule(tenantId, toScheduleCreate(values)),
    onSuccess: async () => {
      setOpen(false);
      form.resetFields();
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "schedules"] });
    },
  });
  const data = schedules.data?.filter((item) => item.agent_id === agent.id) ?? [];
  const defaultTimezone = auth.session?.default_schedule_timezone;
  const openCreate = () => {
    form.setFieldsValue({
      agent_id: agent.id,
      schedule_type: "recurring",
      timezone: defaultTimezone,
    });
    setOpen(true);
  };

  return (
    <section className="agent-tab-panel">
      <div className="agent-tab-heading">
        <div>
          <h2>定时任务</h2>
          <p>当前 Agent：{agent.name}。任务会以已发布运行配置执行。</p>
        </div>
        <Space wrap>
          <Link className="ant-btn" to="/admin/schedules">
            查看全部任务
          </Link>
          {canManage ? (
            <Button type="primary" disabled={!agent.published} onClick={openCreate}>
              新建定时任务
            </Button>
          ) : null}
        </Space>
      </div>
      {!agent.published ? (
        <Alert showIcon type="info" message="请先发布 Agent，才能创建定时任务。" />
      ) : null}
      <RequestErrorAlert error={schedules.error} fallback="加载定时任务失败" />
      <DataTable<Schedule>
        rowKey="id"
        loading={schedules.isPending}
        dataSource={data}
        scroll={{ x: 980 }}
        locale={{ emptyText: "当前 Agent 暂无定时任务" }}
        columns={[
          {
            title: "任务",
            dataIndex: "title",
            width: 280,
            render: (title: string, item) => (
              <div className="agent-schedule-title">
                <strong>{title}</strong>
                <span>{item.input_text}</span>
              </div>
            ),
          },
          {
            title: "类型",
            dataIndex: "schedule_type",
            width: 100,
            render: (type: string) => (
              <Tag color="blue">{type === "once" ? "一次性" : "周期性"}</Tag>
            ),
          },
          {
            title: "触发配置",
            key: "timing",
            width: 200,
            render: (_, item) => item.cron_expr ?? formatDateTime(item.run_at),
          },
          { title: "时区", dataIndex: "timezone", width: 160 },
          { title: "下次触发", dataIndex: "next_trigger_at", width: 190, render: formatDateTime },
          { title: "上次触发", dataIndex: "last_triggered_at", width: 190, render: formatDateTime },
          {
            title: "状态",
            dataIndex: "status",
            width: 90,
            render: (status: string) => (
              <Tag color={status === "enabled" ? "green" : "default"}>
                {status === "enabled" ? "启用" : "停用"}
              </Tag>
            ),
          },
        ]}
      />
      <ScheduleModal
        open={open}
        form={form}
        agents={[{ label: agent.name, value: agent.id }]}
        loading={create.isPending}
        error={create.error}
        defaultTimezone={defaultTimezone}
        onCancel={() => {
          setOpen(false);
          form.resetFields();
        }}
        onSubmit={(values) => create.mutate(values)}
      />
    </section>
  );
}
