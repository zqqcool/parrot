import { Button, Select, Tag } from "antd";

import type { Run } from "@/shared/api/types";
import { formatDateTime } from "@/shared/time";
import { DataTable, type DataTableProps } from "@/shared/ui";

type RunProgressTableProps = {
  loading: boolean;
  runs: Run[] | undefined;
  onView: (run: Run) => void;
};

export function RunProgressTable({ loading, runs, onView }: RunProgressTableProps) {
  return (
    <DataTable
      rowKey="id"
      loading={loading}
      dataSource={runs}
      columns={columns(onView)}
      scroll={{ x: 900 }}
    />
  );
}

export function RunStatusFilter({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Select
      aria-label="选择运行状态"
      options={[
        { label: "全部状态", value: "" },
        { label: "执行中", value: "accepted" },
        { label: "已完成", value: "completed" },
        { label: "失败", value: "failed" },
      ]}
      placeholder="选择运行状态"
      style={{ width: 140 }}
      value={value}
      onChange={onChange}
    />
  );
}

function columns(onView: (run: Run) => void): DataTableProps<Run>["columns"] {
  return [
    { title: "Run ID", dataIndex: "id", ellipsis: true, width: 230 },
    { title: "Agent", dataIndex: "agent_name", width: 170 },
    { title: "来源", dataIndex: "entry_type", width: 100 },
    { title: "输入摘要", dataIndex: "input_summary", ellipsis: true },
    { title: "状态", dataIndex: "status", width: 110, render: statusTag },
    { title: "开始时间", dataIndex: "created_at", width: 180, render: formatDateTime },
    {
      title: "操作",
      key: "actions",
      fixed: "right",
      width: 100,
      render: (_value, run) => (
        <Button size="small" type="link" onClick={() => onView(run)}>
          查看详情
        </Button>
      ),
    },
  ];
}

function statusTag(value: string) {
  const color = value === "completed" ? "success" : value === "failed" ? "error" : "processing";
  return <Tag color={color}>{value}</Tag>;
}
