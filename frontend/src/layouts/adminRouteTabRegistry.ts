export type AdminRouteTab = {
  path: string;
  title: string;
  pinned: boolean;
};

const STORAGE_KEY = "parrot.admin.route-tabs.v1";

const routeTitles: Record<string, string> = {
  "/admin": "工作台",
  "/admin/agents": "智能体管理",
  "/admin/audit": "审计日志",
  "/admin/groups": "用户组管理",
  "/admin/llm-configs": "模型配置",
  "/admin/knowledge": "知识库",
  "/admin/knowledge/new": "新建知识库",
  "/admin/mcp-servers": "MCP 配置",
  "/admin/system-capabilities": "系统能力",
  "/admin/memory": "记忆管理",
  "/admin/roles": "角色与权限",
  "/admin/skills": "Skill 管理",
  "/admin/runs": "运行进度",
  "/admin/schedules": "定时任务",
  "/admin/tenants": "租户管理",
  "/admin/users": "用户管理",
};

const agentWorkspacePattern = /^\/admin\/agents\/[^/]+$/;
const knowledgeDocumentsPattern = /^\/admin\/knowledge\/[^/]+\/documents$/;
const knowledgeDocumentDetailPattern = /^\/admin\/knowledge\/[^/]+\/documents\/[^/]+$/;
const knowledgeRetrievalPattern = /^\/admin\/knowledge\/[^/]+\/retrieval$/;
const requesterRunsPattern = /^\/admin\/runs\/requesters\/[^/]+\/[^/]+$/;
const skillDetailPattern = /^\/admin\/skills\/[^/]+(?:\/edit)?$/;
const systemSkillPattern = /^\/admin\/system-capabilities\/skills\/[^/]+(?:\/edit)?$/;

const dynamicRouteTitles = [
  [agentWorkspacePattern, () => "智能体详情"],
  [knowledgeDocumentsPattern, () => "知识库文档"],
  [knowledgeDocumentDetailPattern, () => "文档分段"],
  [knowledgeRetrievalPattern, () => "召回测试"],
  [requesterRunsPattern, () => "用户运行进度"],
  [
    skillDetailPattern,
    (path: string) => (path.endsWith("/edit") ? "Skill 文件编辑" : "Skill 详情"),
  ],
  [
    systemSkillPattern,
    (path: string) => (path.endsWith("/edit") ? "系统 Skill 文件编辑" : "系统 Skill 详情"),
  ],
] as const;

function isKnownRoute(path: string) {
  return path in routeTitles || dynamicRouteTitles.some(([pattern]) => pattern.test(path));
}

function resolveTitle(path: string) {
  const matched = dynamicRouteTitles.find(([pattern]) => pattern.test(path));
  return matched?.[1](path) ?? routeTitles[path] ?? "管理页面";
}

export const dashboardTab: AdminRouteTab = {
  path: "/admin",
  title: routeTitles["/admin"],
  pinned: true,
};

export function resolveAdminRouteTab(path: string): AdminRouteTab {
  return {
    path,
    title: resolveTitle(path),
    pinned: path === dashboardTab.path,
  };
}

export function loadAdminRouteTabs(): AdminRouteTab[] {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "[]") as AdminRouteTab[];
    const valid = saved.filter(
      (tab) =>
        typeof tab.path === "string" && typeof tab.title === "string" && isKnownRoute(tab.path),
    );
    return [dashboardTab, ...valid.filter((tab) => tab.path !== dashboardTab.path)];
  } catch (error) {
    console.warn("Unable to restore admin route tabs", error);
    return [dashboardTab];
  }
}

export function saveAdminRouteTabs(tabs: AdminRouteTab[]) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(tabs));
  } catch (error) {
    console.warn("Unable to persist admin route tabs", error);
  }
}
