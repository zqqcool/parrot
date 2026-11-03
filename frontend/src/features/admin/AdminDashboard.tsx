import { useQuery } from "@tanstack/react-query";
import { Skeleton, Tag } from "antd";

import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import type { DashboardOverview } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { AppIcon, type AppIconName } from "@/shared/icons";
import { RequestErrorAlert } from "@/shared/ui";

const metricDefinitions: Array<{
  key: keyof Pick<
    DashboardOverview,
    "agents" | "llm_configs" | "skills" | "mcp_servers" | "im_entries" | "runs"
  >;
  label: string;
  icon: AppIconName;
  tone: string;
}> = [
  { key: "agents", label: "Agent", icon: "RobotOne", tone: "violet" },
  { key: "llm_configs", label: "模型配置", icon: "SettingTwo", tone: "cyan" },
  { key: "skills", label: "Skill", icon: "Permissions", tone: "purple" },
  { key: "mcp_servers", label: "MCP 配置", icon: "ApplicationOne", tone: "blue" },
  { key: "im_entries", label: "IM 接入", icon: "Message", tone: "green" },
  { key: "runs", label: "Run", icon: "History", tone: "orange" },
];

export function AdminDashboard() {
  const auth = useAuth();
  const tenantId = useTenantId();
  const tenantName = auth.session?.principal.tenants.find((item) => item.id === tenantId)?.name;
  const query = useQuery({
    queryKey: ["admin", tenantId, "dashboard"],
    queryFn: () => adminApi.dashboard(tenantId ?? ""),
    enabled: Boolean(tenantId),
  });

  return (
    <section className="skyler-dashboard">
      <header className="skyler-dashboard-heading">
        <div>
          <p className="skyler-breadcrumb">
            工作台&nbsp; / &nbsp;{tenantName ?? "当前租户"} Parrot
          </p>
          <h1>智能体平台总览</h1>
        </div>
      </header>

      <RequestErrorAlert error={query.error} fallback="加载工作台失败，请稍后重试。" />
      {query.isPending ? (
        <DashboardSkeleton />
      ) : query.data ? (
        <DashboardBody data={query.data} />
      ) : null}
    </section>
  );
}

function DashboardSkeleton() {
  return (
    <div className="skyler-dashboard-loading">
      <Skeleton active paragraph={{ rows: 8 }} />
    </div>
  );
}

function DashboardBody({ data }: { data: DashboardOverview }) {
  return (
    <>
      <div className="skyler-metrics">
        {metricDefinitions.map((definition) => {
          const metric = data[definition.key];
          return (
            <article className="skyler-metric" key={definition.key}>
              <div className={`skyler-metric-icon ${definition.tone}`}>
                <AppIcon name={definition.icon} size="xl" />
              </div>
              <div>
                <span>{definition.label}</span>
                <strong>{metric.supported ? metric.value : "—"}</strong>
              </div>
              {!metric.supported && <Tag>未开放</Tag>}
            </article>
          );
        })}
      </div>

      <div className="skyler-panels">
        <section className="skyler-panel">
          <div className="skyler-panel-heading">
            <div>
              <h2>服务状态</h2>
              <p>parrot-runtime / {data.service.runtime}</p>
            </div>
            <Tag color={data.service.health === "healthy" ? "success" : "warning"}>
              {data.service.health === "healthy" ? "运行正常" : "服务降级"}
            </Tag>
          </div>
          <dl className="skyler-status-list">
            <StatusRow label="Health" value={data.service.health} />
            <StatusRow label="Database" value={data.service.database} />
            <StatusRow label="Redis" value={data.service.redis} />
            <StatusRow label="Environment" value={data.service.environment} />
            <StatusRow label="Active Run" value={String(data.active_runs)} />
          </dl>
        </section>

        <section className="skyler-panel skyler-dependencies">
          <div className="skyler-panel-heading">
            <div>
              <h2>依赖检查</h2>
              <p>{data.dependency_warnings.length ? "发现需要关注的依赖" : "所有已接入依赖可用"}</p>
            </div>
            <Tag color={data.dependency_warnings.length ? "warning" : "success"}>
              {data.dependency_warnings.length ? "需要关注" : "检查通过"}
            </Tag>
          </div>
          <div className="skyler-dependency-content">
            <AppIcon
              name={data.dependency_warnings.length ? "Audit" : "ApplicationOne"}
              size="3xl"
            />
            <strong>
              {data.dependency_warnings.length
                ? data.dependency_warnings.join("、")
                : "暂无依赖异常"}
            </strong>
            <span>状态来自 Parrot 后端 readiness 与当前租户运行数据</span>
          </div>
        </section>
      </div>
    </>
  );
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
