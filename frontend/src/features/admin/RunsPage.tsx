import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Select } from "antd";
import { useNavigate } from "react-router-dom";

import { RunRequesterTable } from "@/features/admin/RunRequesterTable";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import { AdminPageHeader, RequestErrorAlert, SearchBar, useDebouncedValue } from "@/shared/ui";

export function RunsPage() {
  const navigate = useNavigate();
  const tenantId = useTenantId();
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const [actorTypeFilter, setActorTypeFilter] = useState<"all" | "user" | "anonymous">("all");
  const query = useQuery({
    queryKey: ["admin", tenantId, "runs", "requesters", searchQuery, actorTypeFilter],
    queryFn: () =>
      adminApi.listRunRequesters(tenantId ?? "", {
        actorType: actorTypeFilter === "all" ? "" : actorTypeFilter,
        query: searchQuery,
      }),
    enabled: Boolean(tenantId),
    refetchInterval: 5_000,
  });

  if (!tenantId) return <TenantRequiredState />;
  return (
    <section>
      <AdminPageHeader
        title="运行进度"
        description="按提问用户聚合运行记录；选择一位用户后可查看其对应的运行进度。"
      />
      <SearchBar
        advancedFilters={
          <Select
            aria-label="按身份筛选提问用户"
            options={[
              { value: "all", label: "全部身份" },
              { value: "user", label: "租户用户" },
              { value: "anonymous", label: "匿名访客" },
            ]}
            value={actorTypeFilter}
            onChange={setActorTypeFilter}
          />
        }
        hasActiveFilters={actorTypeFilter !== "all"}
        placeholder="搜索提问用户或身份标识"
        value={searchValue}
        onChange={setSearchValue}
        onReset={() => {
          setSearchValue("");
          setActorTypeFilter("all");
        }}
      />
      <RequestErrorAlert error={query.error} fallback="加载提问用户失败" />
      <RunRequesterTable
        loading={query.isFetching}
        resetPaginationKey={`${searchQuery}:${actorTypeFilter}`}
        requesters={query.data ?? []}
        onSelect={(requester) =>
          void navigate(
            `/admin/runs/requesters/${encodeURIComponent(requester.actor_type)}/${encodeURIComponent(
              requester.actor_id,
            )}`,
          )
        }
      />
    </section>
  );
}
