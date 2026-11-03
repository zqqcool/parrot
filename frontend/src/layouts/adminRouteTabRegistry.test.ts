import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  dashboardTab,
  loadAdminRouteTabs,
  resolveAdminRouteTab,
  saveAdminRouteTabs,
} from "@/layouts/adminRouteTabRegistry";

describe("admin route tab registry", () => {
  beforeEach(() => sessionStorage.clear());

  it("restores known tabs while keeping the dashboard pinned first", () => {
    saveAdminRouteTabs([
      { path: "/admin/users", title: "用户管理", pinned: true },
      { path: "/admin/agents/agent_test", title: "智能体详情", pinned: false },
      { path: "/unknown", title: "Unknown", pinned: false },
    ]);

    expect(loadAdminRouteTabs()).toEqual([
      dashboardTab,
      { path: "/admin/users", title: "用户管理", pinned: true },
      { path: "/admin/agents/agent_test", title: "智能体详情", pinned: false },
    ]);
  });

  it("falls back safely when persisted state is invalid", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    sessionStorage.setItem("parrot.admin.route-tabs.v1", "invalid-json");

    expect(loadAdminRouteTabs()).toEqual([dashboardTab]);
    expect(warn).toHaveBeenCalledOnce();
    warn.mockRestore();
  });

  it("resolves titles for platform routes", () => {
    expect(resolveAdminRouteTab("/admin/agents")).toEqual({
      path: "/admin/agents",
      title: "智能体管理",
      pinned: false,
    });
    expect(resolveAdminRouteTab("/admin/agents/agent_test")).toEqual({
      path: "/admin/agents/agent_test",
      title: "智能体详情",
      pinned: false,
    });
    expect(resolveAdminRouteTab("/admin/runs").title).toBe("运行进度");
    expect(resolveAdminRouteTab("/admin/memory").title).toBe("记忆管理");
    expect(resolveAdminRouteTab("/admin/knowledge").title).toBe("知识库");
    expect(resolveAdminRouteTab("/admin/knowledge/new").title).toBe("新建知识库");
    expect(resolveAdminRouteTab("/admin/knowledge/space_test/documents").title).toBe("知识库文档");
    expect(resolveAdminRouteTab("/admin/knowledge/space_test/documents/document_test").title).toBe(
      "文档分段",
    );
    expect(resolveAdminRouteTab("/admin/knowledge/space_test/retrieval").title).toBe("召回测试");
    expect(resolveAdminRouteTab("/admin/schedules").title).toBe("定时任务");
    expect(resolveAdminRouteTab("/admin/system-capabilities").title).toBe("系统能力");
    expect(resolveAdminRouteTab("/admin/system-capabilities/skills/skill_test/edit").title).toBe(
      "系统 Skill 文件编辑",
    );
  });
});
