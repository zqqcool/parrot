import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Form, Tabs } from "antd";

import { AgentMemorySearchPanel } from "@/features/admin/AgentMemorySearchPanel";
import { CreateMemoryModal, EditMemoryModal } from "@/features/admin/MemoryModals";
import { MemoryRecordsTab, type MemoryStatusFilter } from "@/features/admin/MemoryRecordsTab";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import type { Memory, MemoryCreate } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { AdminPageHeader, useDebouncedValue } from "@/shared/ui";

import "./memory-page.css";

export function MemoryPage() {
  const tenantId = useTenantId();
  const auth = useAuth();
  const client = useQueryClient();
  const [selected, setSelected] = useState<Memory | null>(null);
  const [creating, setCreating] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const [statusFilter, setStatusFilter] = useState<MemoryStatusFilter>("unarchived");
  const [form] = Form.useForm<MemoryCreate>();
  const canManage = auth.hasPermission("memory.manage");
  const query = useQuery({
    queryKey: ["admin", tenantId, "memory", searchQuery, statusFilter],
    queryFn: () =>
      adminApi.listMemory(
        tenantId ?? "",
        searchQuery,
        statusFilter === "unarchived" ? "" : statusFilter,
      ),
    enabled: Boolean(tenantId),
  });
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", tenantId, "memory"] });
  const create = useMutation({
    mutationFn: (payload: MemoryCreate) => adminApi.createMemory(tenantId ?? "", payload),
    onSuccess: async () => {
      setCreating(false);
      form.resetFields();
      await refresh();
    },
  });
  const update = useMutation({
    mutationFn: (content: string) =>
      adminApi.updateMemory(tenantId ?? "", selected?.id ?? "", {
        content,
        expected_version: selected?.version ?? 1,
      }),
    onSuccess: async () => {
      setSelected(null);
      await refresh();
    },
  });
  const archive = useMutation({
    mutationFn: (item: Memory) => adminApi.archiveMemory(tenantId ?? "", item.id, item.version),
    onSuccess: refresh,
  });
  if (!tenantId) return <TenantRequiredState />;
  const memories = query.data ?? [];
  return (
    <section>
      <AdminPageHeader
        title="记忆管理"
        description="管理租户、Agent 与会话范围的结构化记忆；更新采用版本校验，避免并发覆盖。"
      />
      <Tabs
        className="memory-page-tabs"
        defaultActiveKey="records"
        size="small"
        items={[
          {
            key: "records",
            label: "记忆记录",
            children: (
              <MemoryRecordsTab
                tenantId={tenantId}
                canManage={canManage}
                memories={memories}
                queryError={query.error}
                loading={query.isFetching}
                searchQuery={searchQuery}
                searchValue={searchValue}
                statusFilter={statusFilter}
                onCreate={() => setCreating(true)}
                onReset={() => {
                  setSearchValue("");
                  setStatusFilter("unarchived");
                }}
                onSearchChange={setSearchValue}
                onStatusChange={setStatusFilter}
                onEdit={setSelected}
                onArchive={(item) => archive.mutate(item)}
              />
            ),
          },
          {
            key: "agent-view",
            label: "Agent 视角检索",
            children: <AgentMemorySearchPanel tenantId={tenantId} />,
          },
        ]}
      />
      <CreateMemoryModal
        open={creating}
        form={form}
        loading={create.isPending}
        error={create.error}
        onCancel={() => setCreating(false)}
        onSubmit={(payload) => create.mutate(payload)}
      />
      <EditMemoryModal
        memory={selected}
        loading={update.isPending}
        error={update.error}
        onCancel={() => setSelected(null)}
        onSubmit={(content) => update.mutate(content)}
      />
    </section>
  );
}
