import { Button, Descriptions, Popconfirm, Select, Space, Tag, Typography } from "antd";

import type { Memory } from "@/shared/api/types";
import { formatDateTime } from "@/shared/time";
import {
  CreateButton,
  DataTable,
  type DataTableProps,
  RequestErrorAlert,
  SearchBar,
  UserIdentity,
} from "@/shared/ui";

const { Text } = Typography;

export type MemoryStatusFilter = "unarchived" | "active" | "pending_confirmation" | "archived";

type MemoryRecordsTabProps = {
  tenantId: string;
  canManage: boolean;
  memories: Memory[];
  queryError: unknown;
  loading: boolean;
  searchQuery: string;
  searchValue: string;
  statusFilter: MemoryStatusFilter;
  onCreate: () => void;
  onReset: () => void;
  onSearchChange: (value: string) => void;
  onStatusChange: (value: MemoryStatusFilter) => void;
  onEdit: (memory: Memory) => void;
  onArchive: (memory: Memory) => void;
};

export function MemoryRecordsTab({
  tenantId,
  canManage,
  memories,
  queryError,
  loading,
  searchQuery,
  searchValue,
  statusFilter,
  onCreate,
  onReset,
  onSearchChange,
  onStatusChange,
  onEdit,
  onArchive,
}: MemoryRecordsTabProps) {
  return (
    <>
      <SearchBar
        actions={canManage ? <CreateButton onClick={onCreate} /> : null}
        advancedFilters={
          <Select
            aria-label="按状态筛选记忆"
            options={statusOptions}
            value={statusFilter}
            onChange={onStatusChange}
          />
        }
        hasActiveFilters={statusFilter !== "unarchived"}
        placeholder="搜索 Key、内容或范围 ID"
        value={searchValue}
        onChange={onSearchChange}
        onReset={onReset}
      />
      <RequestErrorAlert error={queryError} fallback="加载记忆失败" />
      <DataTable<Memory>
        rowKey="id"
        loading={loading}
        dataSource={memories}
        resetPaginationKey={`${searchQuery}:${statusFilter}`}
        expandable={{
          columnWidth: 48,
          expandedRowRender: (item) => memoryDetails(tenantId, item),
        }}
        columns={memoryColumns(canManage, onEdit, onArchive)}
      />
    </>
  );
}

const statusOptions = [
  { value: "unarchived", label: "未归档" },
  { value: "active", label: "生效" },
  { value: "pending_confirmation", label: "待确认" },
  { value: "archived", label: "已归档" },
] satisfies { value: MemoryStatusFilter; label: string }[];

function memoryColumns(
  canManage: boolean,
  onEdit: (memory: Memory) => void,
  onArchive: (memory: Memory) => void,
): DataTableProps<Memory>["columns"] {
  return [
    { title: "Key", dataIndex: "key", ellipsis: true, width: 220 },
    { title: "类型", dataIndex: "memory_type", width: 160 },
    { title: "内容摘要", dataIndex: "content", ellipsis: true },
    { title: "状态", dataIndex: "status", width: 90, render: memoryStatus },
    {
      title: "操作",
      key: "actions",
      width: 150,
      render: (_, item) => actionCell(canManage, item, onEdit, onArchive),
    },
  ];
}

function memoryDetails(tenantId: string, item: Memory) {
  return (
    <Descriptions
      bordered
      size="small"
      column={{ xs: 1, sm: 2, lg: 3 }}
      items={[
        {
          key: "content",
          label: "完整内容",
          span: { xs: 1, sm: 2, lg: 3 },
          children: (
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>
              {item.content}
            </Typography.Paragraph>
          ),
        },
        { key: "agent", label: "归属 Agent", children: agentCell(item) },
        { key: "creator", label: "创建者", children: creatorCell(tenantId, item) },
        {
          key: "scope",
          label: "范围",
          children: `${item.scope_type} / ${item.scope_id}`,
        },
        { key: "created_at", label: "创建时间", children: formatDateTime(item.created_at) },
        { key: "updated_at", label: "更新时间", children: formatDateTime(item.updated_at) },
        { key: "version", label: "版本", children: item.version },
        { key: "retention", label: "保留策略", children: item.retention_policy },
        { key: "id", label: "记忆 ID", children: <MetaId value={item.id} /> },
      ]}
    />
  );
}

function agentCell(item: Memory) {
  if (!item.agent_id) return <Text type="secondary">未绑定 Agent</Text>;
  return (
    <Space direction="vertical" size={0}>
      <Text>{item.agent_name ?? item.agent_id}</Text>
      {item.agent_name ? <MetaId value={item.agent_id} /> : null}
    </Space>
  );
}

function creatorCell(tenantId: string, item: Memory) {
  return (
    <Space direction="vertical" size={0}>
      {item.created_by ? (
        <UserIdentity tenantId={tenantId} user={item.created_by} />
      ) : (
        <Text>{item.created_by_actor_id.startsWith("visitor_") ? "匿名访客" : "创建主体"}</Text>
      )}
      <MetaId value={item.created_by_actor_id} />
    </Space>
  );
}

function MetaId({ value }: { value: string }) {
  return (
    <Text type="secondary" ellipsis={{ tooltip: value }} style={{ maxWidth: 190 }}>
      {value}
    </Text>
  );
}

function actionCell(
  canManage: boolean,
  item: Memory,
  onEdit: (memory: Memory) => void,
  onArchive: (memory: Memory) => void,
) {
  if (!canManage) return "-";
  return (
    <Space>
      <Button
        type="link"
        size="small"
        disabled={item.status !== "active"}
        onClick={() => onEdit(item)}
      >
        编辑
      </Button>
      <Popconfirm title="归档后不可继续编辑，确认归档？" onConfirm={() => onArchive(item)}>
        <Button type="link" danger size="small" disabled={item.status !== "active"}>
          归档
        </Button>
      </Popconfirm>
    </Space>
  );
}

function memoryStatus(value: string) {
  const labels = { active: "生效", pending_confirmation: "待确认", archived: "已归档" };
  return (
    <Tag
      color={
        value === "active" ? "success" : value === "pending_confirmation" ? "warning" : "default"
      }
    >
      {labels[value as keyof typeof labels] ?? value}
    </Tag>
  );
}
