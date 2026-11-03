import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Tag } from "antd";

import { AgentMemorySearchControls } from "@/features/admin/AgentMemorySearchControls";
import { adminApi } from "@/shared/api/client";
import type { AgentMemorySearchPage, Memory } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { DataTable, RequestErrorAlert, useDebouncedValue } from "@/shared/ui";

type Props = {
  tenantId: string;
};
type PageState = {
  current: number;
  size: number;
};
const EMPTY_MEMORY_PAGE: AgentMemorySearchPage = {
  items: [],
  total: 0,
  offset: 0,
  limit: 20,
  mode: "browse",
  anchor_id: null,
  retrieval_method: "browse",
  degradation_reason: null,
};

export function AgentMemorySearchPanel({ tenantId }: Props) {
  const auth = useAuth();
  const canReadAgents = auth.hasPermission("agents.read");
  const canReadUsers = auth.hasPermission("tenant.users.read");

  return (
    <>
      <p>复用运行时 memory 工具的可见性与关键词规则，不调用 LLM，也不包含历史消息。</p>
      {canReadAgents ? (
        <AgentMemorySearchWorkspace tenantId={tenantId} canReadUsers={canReadUsers} />
      ) : (
        <Alert showIcon type="info" message="当前账号没有查看 Agent 上下文记忆的权限。" />
      )}
    </>
  );
}

function AgentMemorySearchWorkspace({ canReadUsers, tenantId }: Props & { canReadUsers: boolean }) {
  const [agentId, setAgentId] = useState<string>();
  const [actorId, setActorId] = useState<string>();
  const [searchValue, setSearchValue] = useState("");
  const [page, setPage] = useState<PageState>({ current: 1, size: 20 });
  const searchQuery = useDebouncedValue(searchValue.trim());
  const agents = useQuery({
    queryKey: ["admin", tenantId, "agents", "memory-agent-view"],
    queryFn: () => adminApi.listAgents(tenantId),
  });
  const users = useQuery({
    queryKey: ["admin", tenantId, "users", "memory-agent-view"],
    queryFn: () => adminApi.listUsers(tenantId),
    enabled: canReadUsers,
  });
  const memories = useQuery({
    queryKey: memoryQueryKey(tenantId, agentId, actorId, searchQuery, page),
    queryFn: () =>
      adminApi.searchAgentMemory(tenantId, {
        agentId: agentId ?? "",
        actorId,
        query: searchQuery,
        offset: (page.current - 1) * page.size,
        limit: page.size,
      }),
    enabled: Boolean(agentId),
  });
  const resetPage = (size = page.size) => setPage({ current: 1, size });
  const agentOptions = agents.data ?? [];
  const userOptions = users.data ?? [];
  const memoryData = memories.data ?? EMPTY_MEMORY_PAGE;

  return (
    <>
      <AgentMemorySearchControls
        agents={agentOptions}
        actorId={actorId}
        agentId={agentId}
        canReadUsers={canReadUsers}
        loadingAgents={agents.isPending}
        loadingUsers={users.isPending}
        searchValue={searchValue}
        users={userOptions}
        onActorChange={(value) => {
          setActorId(value);
          resetPage();
        }}
        onAgentChange={(value) => {
          setAgentId(value);
          setActorId(undefined);
          resetPage();
        }}
        onReset={() => {
          setAgentId(undefined);
          setActorId(undefined);
          setSearchValue("");
          resetPage(20);
        }}
        onSearchChange={(value) => {
          setSearchValue(value);
          resetPage();
        }}
      />
      <RequestErrorAlert
        error={firstError(agents.error, users.error, memories.error)}
        fallback="加载 Agent 视角记忆失败"
      />
      <AgentMemorySearchResults
        agentId={agentId}
        anchorId={memoryData.anchor_id}
        items={memoryData.items}
        loading={memories.isFetching}
        mode={memoryData.mode}
        page={page}
        retrievalMethod={memoryData.retrieval_method}
        degradationReason={memoryData.degradation_reason}
        searchQuery={searchQuery}
        total={memoryData.total}
        actorId={actorId}
        onPageChange={(current, size) => setPage({ current, size })}
      />
    </>
  );
}

function AgentMemorySearchResults({
  agentId,
  anchorId,
  actorId,
  items,
  loading,
  mode,
  page,
  retrievalMethod,
  degradationReason,
  searchQuery,
  total,
  onPageChange,
}: {
  agentId: string | undefined;
  anchorId: string | null | undefined;
  actorId: string | undefined;
  items: Memory[];
  loading: boolean;
  mode: "browse" | "window";
  page: PageState;
  retrievalMethod: "browse" | "hybrid" | "lexical" | "lexical_fallback";
  degradationReason: string | null | undefined;
  searchQuery: string;
  total: number;
  onPageChange: (current: number, size: number) => void;
}) {
  if (!agentId) {
    return <Alert showIcon type="info" message="请选择 Agent 后查看其运行时可见记忆。" />;
  }
  return (
    <>
      {mode === "window" ? (
        <Alert
          showIcon
          type={retrievalMethod === "lexical_fallback" ? "warning" : "info"}
          message={retrievalLabel(
            retrievalMethod,
            degradationReason,
            items.find((item) => item.id === anchorId)?.key,
          )}
        />
      ) : null}
      <DataTable<Memory>
        rowKey="id"
        loading={loading}
        dataSource={items}
        locale={{ emptyText: "该上下文没有可见记忆" }}
        pagination={
          mode === "window"
            ? false
            : {
                current: page.current,
                pageSize: page.size,
                total,
                onChange: onPageChange,
                showTotal: (value) => `共 ${value} 条`,
              }
        }
        resetPaginationKey={`${agentId}:${actorId ?? ""}:${searchQuery}`}
        columns={memoryColumns}
      />
    </>
  );
}

function memoryQueryKey(
  tenantId: string,
  agentId: string | undefined,
  actorId: string | undefined,
  query: string,
  page: PageState,
) {
  return [
    "admin",
    tenantId,
    "memory",
    "agent-view",
    agentId,
    actorId,
    query,
    page.current,
    page.size,
  ];
}

function firstError(...errors: unknown[]) {
  return errors.find(Boolean) ?? null;
}

const memoryColumns = [
  { title: "Key", dataIndex: "key", width: 180 },
  {
    title: "范围",
    key: "scope",
    width: 180,
    render: (_: unknown, item: Memory) => `${item.scope_type} / ${item.scope_id}`,
  },
  { title: "类型", dataIndex: "memory_type", width: 160 },
  { title: "内容", dataIndex: "content", ellipsis: true },
  { title: "状态", dataIndex: "status", width: 100, render: agentMemoryStatus },
];

function agentMemoryStatus(value: string) {
  const labels = { active: "生效", pending_confirmation: "待确认" };
  return (
    <Tag color={value === "active" ? "success" : "warning"}>
      {labels[value as keyof typeof labels] ?? value}
    </Tag>
  );
}

function retrievalLabel(method: string, reason: string | null | undefined, anchorKey?: string) {
  const anchor = anchorKey ? `锚点：${anchorKey}。` : "";
  if (method === "hybrid") return `混合检索：${anchor}已返回同一范围内的前后上下文。`;
  if (method === "lexical_fallback") {
    return `词法检索降级：${anchor}向量检索暂不可用${reason ? `（${reason}）` : ""}。`;
  }
  return `词法检索：${anchor}已返回同一范围内的前后上下文。`;
}
