import { Avatar, Button, Dropdown, Flex, Layout, Menu, Select } from "antd";
import type { MenuProps } from "antd";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { AdminRouteTabs } from "@/layouts/AdminRouteTabs";
import { AdminAgentSidebar, type AdminAgentNavigationItem } from "@/layouts/AdminAgentSidebar";
import { CurrentUserProfileModal } from "@/features/account/CurrentUserProfileModal";
import { endpoints } from "@/shared/api/endpoints";
import type { Principal } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { ParrotLogo } from "@/shared/brand";
import { AppIcon } from "@/shared/icons";

type PermissionNavigationItem = AdminAgentNavigationItem & { permission: string };

const accessNavigation: PermissionNavigationItem[] = [
  {
    to: "/admin/tenants",
    label: "租户管理",
    icon: "Dashboard",
    permission: "platform.tenants.manage",
  },
  { to: "/admin/users", label: "用户管理", icon: "People", permission: "tenant.users.read" },
  {
    to: "/admin/groups",
    label: "用户组管理",
    icon: "ApplicationOne",
    permission: "tenant.groups.read",
  },
  { to: "/admin/roles", label: "角色与权限", icon: "Permissions", permission: "tenant.roles.read" },
];

const workspaceNavigation: AdminAgentNavigationItem[] = [
  { to: "/admin", label: "总览", icon: "Workbench" },
  {
    to: "/admin/agents",
    label: "智能体管理",
    icon: "RobotOne",
    permission: "agents.read",
  },
  {
    to: "/admin/llm-configs",
    label: "模型配置",
    icon: "SettingTwo",
    permission: "llm_configs.read",
  },
  {
    to: "/admin/skills",
    label: "Skill",
    icon: "Permissions",
    permission: "skills.read",
  },
  {
    to: "/admin/runs",
    label: "运行进度",
    icon: "History",
    permission: "interactions.read.any",
  },
  {
    to: "/admin/memory",
    label: "记忆管理",
    icon: "ApplicationOne",
    permission: "memory.read",
  },
  {
    to: "/admin/knowledge",
    label: "知识库",
    icon: "Folder",
    permission: "knowledge.spaces.read",
  },
  {
    to: "/admin/schedules",
    label: "定时任务",
    icon: "History",
    permission: "schedules.read",
  },
  {
    to: "/admin/mcp-servers",
    label: "MCP 配置",
    icon: "SettingTwo",
    permission: "mcp_servers.read",
  },
];

const utilityNavigation: PermissionNavigationItem[] = [
  { to: "/admin/audit", label: "审计日志", icon: "Audit", permission: "audit.read" },
];

function currentProfileAvatarUrl(principal: Principal | undefined): string | undefined {
  return principal?.avatar_present && principal.tenant_id
    ? `${endpoints.auth.profileAvatar}?v=${encodeURIComponent(principal.request_id)}`
    : undefined;
}

function selectedNavigationKeys(path: string, items: readonly AdminAgentNavigationItem[]) {
  return items
    .filter((item) => (item.to === "/admin" ? path === item.to : path.startsWith(item.to)))
    .map((item) => item.to);
}

function includesNavigationItem(keys: string[], items: readonly AdminAgentNavigationItem[]) {
  return keys.some((key) => items.some((item) => item.to === key));
}

function selectedTopNavigationKeys(
  selectedKeys: string[],
  visibleAccess: AdminAgentNavigationItem[],
) {
  if (includesNavigationItem(selectedKeys, workspaceNavigation.slice(1))) return ["agent"];
  if (includesNavigationItem(selectedKeys, visibleAccess)) return ["access"];
  return selectedKeys;
}

function adminShellClass(maximized: boolean) {
  return maximized ? "admin-shell admin-shell-maximized" : "admin-shell";
}

function adminContentClass(path: string) {
  if (/^\/admin\/skills\/[^/]+\/edit$/.test(path)) {
    return "admin-content admin-content-workspace";
  }
  if (/^\/admin\/knowledge\/[^/]+\/retrieval$/.test(path)) {
    return "admin-content admin-content-retrieval";
  }
  return "admin-content";
}

export function AdminLayout() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const [routeVersion, setRouteVersion] = useState(0);
  const [contentMaximized, setContentMaximized] = useState(false);
  const [agentNavigationCollapsed, setAgentNavigationCollapsed] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const principal = auth.session?.principal;
  const visibleAccess = accessNavigation.filter((item) => auth.hasPermission(item.permission));
  const visibleUtility = utilityNavigation.filter((item) => auth.hasPermission(item.permission));
  const navigationItems: MenuProps["items"] = [
    {
      key: "/admin",
      icon: <AppIcon name="Workbench" size="md" />,
      label: "总览",
    },
    { key: "agent", icon: <AppIcon name="RobotOne" size="md" />, label: "Agent" },
    ...(visibleAccess.length
      ? [
          {
            key: "access",
            icon: <AppIcon name="Permissions" size="md" />,
            label: "组织与权限",
            children: visibleAccess.map((item) => ({
              key: item.to,
              icon: <AppIcon name={item.icon} size="md" />,
              label: item.label,
            })),
          },
        ]
      : []),
    ...visibleUtility.map((item) => ({
      key: item.to,
      icon: <AppIcon name={item.icon} size="md" />,
      label: item.label,
    })),
  ];
  const selectedNavigation = selectedNavigationKeys(location.pathname, [
    ...workspaceNavigation,
    ...visibleAccess,
    ...visibleUtility,
  ]);
  const isAgentRoute = includesNavigationItem(selectedNavigation, workspaceNavigation.slice(1));
  const selectedTopNavigation = selectedTopNavigationKeys(selectedNavigation, visibleAccess);
  const reloadCurrentRoute = (path = location.pathname) => {
    const reload = () =>
      queryClient
        .invalidateQueries({ queryKey: ["admin"], refetchType: "none" })
        .finally(() => setRouteVersion((version) => version + 1));
    if (path === location.pathname) void reload();
    else {
      void navigate(path);
      void reload();
    }
  };

  return (
    <Layout className={adminShellClass(contentMaximized)}>
      <Layout.Header className="admin-header">
        <Flex className="admin-header-inner" align="center">
          <NavLink className="brand-link" to="/admin">
            <ParrotLogo size="small" />
            <span>Parrot 管理控制台</span>
          </NavLink>
          <nav className="admin-nav" aria-label="后台管理">
            <Menu
              mode="horizontal"
              items={navigationItems}
              selectedKeys={selectedTopNavigation}
              onClick={({ key }) => {
                if (key === "agent") void navigate("/admin/agents");
                if (key.startsWith("/")) void navigate(key);
              }}
            />
          </nav>
          <Flex className="admin-actions" align="center" gap="small">
            <div className="tenant-context">
              <span className="tenant-context-label">当前租户</span>
              <Select
                aria-label="当前租户"
                placeholder="选择租户"
                value={principal?.tenant_id ?? undefined}
                options={principal?.tenants.map((tenant) => ({
                  value: tenant.id,
                  label: tenant.name,
                }))}
                onChange={(tenantId) => void auth.switchTenant(tenantId)}
                className="tenant-select"
              />
            </div>
            <Dropdown
              menu={{
                items: [
                  {
                    key: "profile",
                    icon: <AppIcon name="User" size="md" />,
                    label: "个人资料",
                  },
                  { type: "divider" },
                  {
                    key: "logout",
                    danger: true,
                    icon: <AppIcon name="Logout" size="md" />,
                    label: "退出登录",
                  },
                ],
                onClick: ({ key }) => {
                  if (key === "profile") setProfileOpen(true);
                  if (key === "logout") void auth.logout();
                },
              }}
              trigger={["click"]}
            >
              <Button className="admin-user-trigger" type="text" aria-label="打开用户菜单">
                <Avatar size={24} src={currentProfileAvatarUrl(principal)}>
                  {principal?.display_name.slice(0, 1)}
                </Avatar>
                <span>{principal?.display_name}</span>
              </Button>
            </Dropdown>
          </Flex>
        </Flex>
      </Layout.Header>
      <CurrentUserProfileModal
        open={profileOpen}
        principal={principal}
        onClose={() => setProfileOpen(false)}
      />
      <Layout className="admin-main">
        {isAgentRoute ? (
          <AdminAgentSidebar
            collapsed={agentNavigationCollapsed}
            items={workspaceNavigation.slice(1)}
            selectedKeys={selectedNavigation}
            canAccess={auth.hasPermission}
            onCollapsedChange={setAgentNavigationCollapsed}
            onNavigate={(path) => void navigate(path)}
          />
        ) : null}
        <Layout className="admin-work-area">
          <AdminRouteTabs
            maximized={contentMaximized}
            onReload={reloadCurrentRoute}
            onToggleMaximize={() => setContentMaximized((maximized) => !maximized)}
          />
          <Layout.Content className={adminContentClass(location.pathname)}>
            <Outlet key={`${location.pathname}:${routeVersion}`} />
          </Layout.Content>
        </Layout>
      </Layout>
    </Layout>
  );
}
