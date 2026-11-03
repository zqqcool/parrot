import { Button, Tag } from "antd";

import type { RunRequester } from "@/shared/api/types";
import { formatDateTime } from "@/shared/time";
import { DataTable, type DataTableProps } from "@/shared/ui";

type RunRequesterTableProps = {
  loading: boolean;
  resetPaginationKey?: string;
  requesters: RunRequester[] | undefined;
  onSelect: (requester: RunRequester) => void;
};

export function RunRequesterTable({
  loading,
  resetPaginationKey,
  requesters,
  onSelect,
}: RunRequesterTableProps) {
  return (
    <DataTable
      rowKey={(requester) => `${requester.actor_type}:${requester.actor_id}`}
      loading={loading}
      dataSource={requesters}
      resetPaginationKey={resetPaginationKey}
      columns={columns(onSelect)}
      scroll={{ x: 760 }}
    />
  );
}

function columns(
  onSelect: (requester: RunRequester) => void,
): DataTableProps<RunRequester>["columns"] {
  return [
    {
      title: "提问用户",
      dataIndex: "display_name",
      render: (value: string) => <strong>{value}</strong>,
    },
    { title: "身份", dataIndex: "actor_type", width: 130, render: actorTypeTag },
    { title: "运行总数", dataIndex: "run_count", width: 110 },
    {
      title: "进行中",
      dataIndex: "active_run_count",
      width: 100,
      render: (value: number) => <Tag color={value ? "processing" : "default"}>{value}</Tag>,
    },
    { title: "最近提问", dataIndex: "latest_run_at", width: 180, render: formatDateTime },
    {
      title: "操作",
      key: "actions",
      width: 130,
      render: (_value, requester) => (
        <Button size="small" type="link" onClick={() => onSelect(requester)}>
          查看运行
        </Button>
      ),
    },
  ];
}

function actorTypeTag(value: string) {
  if (value === "user") return <Tag color="blue">租户用户</Tag>;
  if (value === "anonymous") return <Tag color="purple">匿名访客</Tag>;
  return <Tag>{value}</Tag>;
}
