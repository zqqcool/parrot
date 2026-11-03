import { Button, Dropdown, Flex, Tabs, Tooltip } from "antd";
import type { MenuProps } from "antd";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  dashboardTab,
  loadAdminRouteTabs,
  resolveAdminRouteTab,
  saveAdminRouteTabs,
  type AdminRouteTab,
} from "@/layouts/adminRouteTabRegistry";
import { AppIcon } from "@/shared/icons";
import type { AppIconName } from "@/shared/icons";

type Props = {
  maximized: boolean;
  onReload: (path?: string) => void;
  onToggleMaximize: () => void;
};

const routeIcons: Record<string, AppIconName> = {
  "/admin": "Workbench",
  "/admin/agents": "RobotOne",
  "/admin/audit": "Audit",
  "/admin/groups": "ApplicationOne",
  "/admin/llm-configs": "SettingTwo",
  "/admin/knowledge": "Folder",
  "/admin/mcp-servers": "SettingTwo",
  "/admin/system-capabilities": "Permissions",
  "/admin/roles": "Permissions",
  "/admin/skills": "Dashboard",
  "/admin/tenants": "Dashboard",
  "/admin/users": "People",
};

function routeIcon(path: string) {
  if (path === "/admin/knowledge/new") return "Folder";
  if (/^\/admin\/agents\/[^/]+$/.test(path)) return "RobotOne";
  if (/^\/admin\/knowledge\/[^/]+\/documents$/.test(path)) return "Folder";
  if (/^\/admin\/knowledge\/[^/]+\/documents\/[^/]+$/.test(path)) return "FileText";
  if (/^\/admin\/knowledge\/[^/]+\/retrieval$/.test(path)) return "Search";
  if (/^\/admin\/runs\/requesters\/[^/]+\/[^/]+$/.test(path)) return "History";
  if (/^\/admin\/skills\/[^/]+/.test(path)) return "Dashboard";
  if (/^\/admin\/system-capabilities\/skills\/[^/]+/.test(path)) return "Permissions";
  return routeIcons[path] ?? "Dashboard";
}

function loadTabsWithCurrentRoute(path: string) {
  const saved = loadAdminRouteTabs();
  const current = resolveAdminRouteTab(path);
  return saved.some((tab) => tab.path === current.path) ? saved : [...saved, current];
}

export function AdminRouteTabs({ maximized, onReload, onToggleMaximize }: Props) {
  const location = useLocation();
  const navigate = useNavigate();
  const [tabs, setTabs] = useState(() => loadTabsWithCurrentRoute(location.pathname));

  useEffect(() => {
    const current = resolveAdminRouteTab(location.pathname);
    setTabs((previous) =>
      previous.some((tab) => tab.path === current.path) ? previous : [...previous, current],
    );
  }, [location.pathname]);

  useEffect(() => saveAdminRouteTabs(tabs), [tabs]);

  const closeTab = (path: string) => {
    const index = tabs.findIndex((tab) => tab.path === path);
    if (index < 0 || tabs[index].pinned) return;
    const remaining = tabs.filter((tab) => tab.path !== path);
    setTabs(remaining);
    if (path === location.pathname) {
      const fallback = remaining[Math.min(index, remaining.length - 1)] ?? dashboardTab;
      void navigate(fallback.path);
    }
  };

  const keepTabs = (predicate: (tab: AdminRouteTab, index: number) => boolean) => {
    const remaining = tabs.filter((tab, index) => tab.pinned || predicate(tab, index));
    setTabs(remaining);
    if (!remaining.some((tab) => tab.path === location.pathname)) void navigate(dashboardTab.path);
  };

  const contextMenu = (tab: AdminRouteTab, index: number): MenuProps => ({
    items: [
      { key: "close", label: "关闭", disabled: tab.pinned },
      {
        key: "pin",
        label: tab.pinned ? "取消固定" : "固定",
        disabled: tab.path === dashboardTab.path,
      },
      { type: "divider" },
      { key: "maximize", label: maximized ? "还原" : "最大化" },
      { key: "reload", label: "重新加载" },
      { key: "new", label: "在新窗口打开" },
      { type: "divider" },
      { key: "left", label: "关闭左侧标签页", disabled: index === 0 },
      { key: "right", label: "关闭右侧标签页", disabled: index === tabs.length - 1 },
      { key: "others", label: "关闭其他标签页" },
      { key: "all", label: "关闭全部标签页" },
    ],
    onClick: ({ key }) => {
      if (key === "close") closeTab(tab.path);
      if (key === "reload") onReload(tab.path);
      if (key === "maximize") onToggleMaximize();
      if (key === "pin")
        setTabs((previous) =>
          previous.map((item) =>
            item.path === tab.path ? { ...item, pinned: !item.pinned } : item,
          ),
        );
      if (key === "new") window.open(tab.path, "_blank", "noopener,noreferrer");
      if (key === "left") keepTabs((_, itemIndex) => itemIndex >= index);
      if (key === "right") keepTabs((_, itemIndex) => itemIndex <= index);
      if (key === "others") keepTabs((item) => item.path === tab.path);
      if (key === "all") keepTabs(() => false);
    },
  });

  const activeIndex = Math.max(
    0,
    tabs.findIndex((tab) => tab.path === location.pathname),
  );
  const activeTab = tabs[activeIndex] ?? dashboardTab;

  return (
    <Flex className="admin-route-bar" align="center">
      <Tooltip title="返回上一页">
        <Button
          className="admin-route-back"
          type="text"
          aria-label="返回上一页"
          icon={<AppIcon name="Back" size="md" theme="filled" />}
          onClick={() => void navigate(-1)}
        />
      </Tooltip>
      <Tabs
        className="admin-route-tabs"
        type="editable-card"
        size="small"
        hideAdd
        tabBarStyle={{ margin: 0 }}
        activeKey={location.pathname}
        items={tabs.map((tab, index) => ({
          key: tab.path,
          closable: !tab.pinned,
          label: (
            <Dropdown trigger={["contextMenu"]} menu={contextMenu(tab, index)}>
              <Flex component="span" gap={5} align="center">
                <AppIcon name={routeIcon(tab.path)} size="md" />
                <span>{tab.title}</span>
                {tab.pinned ? <AppIcon name="Pin" size="xs" /> : null}
              </Flex>
            </Dropdown>
          ),
        }))}
        onTabClick={(path) => {
          if (path !== location.pathname) void navigate(path);
        }}
        onEdit={(path, action) => {
          if (action === "remove" && typeof path === "string") closeTab(path);
        }}
      />
      <Flex className="admin-route-actions" align="center">
        <Dropdown trigger={["click"]} menu={contextMenu(activeTab, activeIndex)}>
          <Button
            type="text"
            aria-label="标签页操作"
            icon={<AppIcon name="AllApplication" size="md" />}
          />
        </Dropdown>
        <Tooltip title="重新加载当前页面">
          <Button
            type="text"
            aria-label="重新加载当前页面"
            icon={<AppIcon name="Refresh" size="md" />}
            onClick={() => onReload()}
          />
        </Tooltip>
        <Tooltip title={maximized ? "还原" : "最大化内容区"}>
          <Button
            type="text"
            aria-label={maximized ? "还原内容区" : "最大化内容区"}
            icon={<AppIcon name={maximized ? "OffScreen" : "FullScreenOne"} size="md" />}
            onClick={onToggleMaximize}
          />
        </Tooltip>
      </Flex>
    </Flex>
  );
}
