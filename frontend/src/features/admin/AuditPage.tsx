import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useTenantId } from "@/features/admin/useTenant";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { adminApi } from "@/shared/api/client";
import { formatDateTime } from "@/shared/time";
import {
  AdminPageHeader,
  DataTable,
  RequestErrorAlert,
  SearchBar,
  useDebouncedValue,
  UserIdentity,
} from "@/shared/ui";

export function AuditPage() {
  const tenantId = useTenantId();
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const query = useQuery({
    queryKey: ["admin", tenantId, "audit", searchQuery],
    queryFn: () => adminApi.listAudit(tenantId ?? "", searchQuery),
    enabled: Boolean(tenantId),
  });
  if (!tenantId) return <TenantRequiredState />;
  return (
    <section>
      <AdminPageHeader title="审计日志" description="查看当前租户最近的安全事件与管理操作。" />
      <SearchBar
        placeholder="搜索操作、资源或请求编号"
        value={searchValue}
        onChange={setSearchValue}
        onReset={() => setSearchValue("")}
      />
      <RequestErrorAlert error={query.error} fallback="加载审计日志失败，请稍后重试。" />
      <DataTable
        rowKey="id"
        loading={query.isFetching}
        dataSource={query.data}
        resetPaginationKey={searchQuery}
        columns={[
          {
            title: "时间",
            dataIndex: "created_at",
            render: formatDateTime,
          },
          { title: "操作", dataIndex: "action" },
          {
            title: "资源",
            render: (_, item) => `${item.resource_type}:${item.resource_id ?? "-"}`,
          },
          {
            title: "操作者",
            dataIndex: "actor",
            render: (_value, item) =>
              item.actor_type === "user" ? (
                <UserIdentity tenantId={tenantId} user={item.actor} />
              ) : (
                item.actor_type
              ),
          },
          { title: "请求编号", dataIndex: "request_id" },
        ]}
      />
    </section>
  );
}
