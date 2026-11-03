import { Button, ConfigProvider, Layout, Menu, Tooltip } from "antd";
import type { MenuProps } from "antd";

import { AppIcon, type AppIconName } from "@/shared/icons";

export type AdminAgentNavigationItem = {
  to: string;
  label: string;
  icon: AppIconName;
  permission?: string;
};

type Props = {
  collapsed: boolean;
  items: readonly AdminAgentNavigationItem[];
  selectedKeys: string[];
  onCollapsedChange: (collapsed: boolean) => void;
  onNavigate: (path: string) => void;
  canAccess: (permission: string) => boolean;
};

export function AdminAgentSidebar({
  collapsed,
  items,
  selectedKeys,
  onCollapsedChange,
  onNavigate,
  canAccess,
}: Props) {
  const menuItems: MenuProps["items"] = items.map((item) => ({
    key: item.to,
    icon: <AppIcon name={item.icon} size="md" />,
    label: item.label,
    disabled: Boolean(item.permission && !canAccess(item.permission)),
  }));
  const collapseLabel = collapsed ? "展开 Agent 导航" : "收起 Agent 导航";

  return (
    <Layout.Sider
      breakpoint="lg"
      className="admin-agent-sidebar"
      collapsed={collapsed}
      collapsedWidth={56}
      theme="light"
      trigger={null}
      width={200}
      onBreakpoint={onCollapsedChange}
    >
      <nav
        className={
          collapsed
            ? "admin-side-navigation admin-side-navigation-collapsed"
            : "admin-side-navigation"
        }
        aria-label="Agent 工作台"
      >
        <div
          className={
            collapsed
              ? "admin-side-navigation-header admin-side-navigation-header-collapsed"
              : "admin-side-navigation-header"
          }
        >
          {!collapsed ? (
            <div className="admin-side-navigation-title">
              <AppIcon name="RobotOne" size="md" />
              <span>Agent 工作台</span>
            </div>
          ) : null}
          <Tooltip placement="right" title={collapseLabel}>
            <Button
              type="text"
              className="admin-side-navigation-trigger"
              aria-label={collapseLabel}
              icon={<AppIcon name={collapsed ? "MenuUnfold" : "MenuFold"} size="md" />}
              onClick={() => onCollapsedChange(!collapsed)}
            />
          </Tooltip>
        </div>
        <ConfigProvider theme={{ components: { Menu: { collapsedWidth: 56 } } }}>
          <Menu
            inlineCollapsed={collapsed}
            mode="inline"
            items={menuItems}
            selectedKeys={selectedKeys}
            onClick={({ key }) => onNavigate(String(key))}
          />
        </ConfigProvider>
      </nav>
    </Layout.Sider>
  );
}
