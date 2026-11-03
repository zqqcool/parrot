import { lazy, Suspense } from "react";
import { Spin } from "antd";
import { Navigate, Route, Routes } from "react-router-dom";

import { AdminLayout } from "@/layouts/AdminLayout";
import { PublicLayout } from "@/layouts/PublicLayout";
import { RequireAuth, RequirePasswordChanged, RequirePermission } from "@/shared/auth/RequireAuth";
import { NotFoundPage } from "./NotFoundPage";

const AdminDashboard = lazy(() =>
  import("@/features/admin/AdminDashboard").then((module) => ({ default: module.AdminDashboard })),
);
const AgentsPage = lazy(() =>
  import("@/features/admin/AgentsPage").then((module) => ({ default: module.AgentsPage })),
);
const AgentWorkspacePage = lazy(() =>
  import("@/features/admin/AgentWorkspacePage").then((module) => ({
    default: module.AgentWorkspacePage,
  })),
);
const LlmConfigsPage = lazy(() =>
  import("@/features/admin/LlmConfigsPage").then((module) => ({ default: module.LlmConfigsPage })),
);
const SkillsPage = lazy(() =>
  import("@/features/admin/SkillsPage").then((module) => ({ default: module.SkillsPage })),
);
const SkillDetailPage = lazy(() =>
  import("@/features/admin/SkillDetailPage").then((module) => ({
    default: module.SkillDetailPage,
  })),
);
const SkillEditorPage = lazy(() =>
  import("@/features/admin/SkillEditorPage").then((module) => ({
    default: module.SkillEditorPage,
  })),
);
const McpServersPage = lazy(() =>
  import("@/features/admin/McpServersPage").then((module) => ({ default: module.McpServersPage })),
);
const AuditPage = lazy(() =>
  import("@/features/admin/AuditPage").then((module) => ({ default: module.AuditPage })),
);
const RunsPage = lazy(() =>
  import("@/features/admin/RunsPage").then((module) => ({ default: module.RunsPage })),
);
const RequesterRunsPage = lazy(() =>
  import("@/features/admin/RequesterRunsPage").then((module) => ({
    default: module.RequesterRunsPage,
  })),
);
const MemoryPage = lazy(() =>
  import("@/features/admin/MemoryPage").then((module) => ({ default: module.MemoryPage })),
);
const KnowledgePage = lazy(() =>
  import("@/features/admin/KnowledgePage").then((module) => ({ default: module.KnowledgePage })),
);
const KnowledgeSpaceCreatePage = lazy(() =>
  import("@/features/admin/KnowledgeSpaceCreateWizard").then((module) => ({
    default: module.KnowledgeSpaceCreatePage,
  })),
);
const KnowledgeDocumentsPage = lazy(() =>
  import("@/features/admin/KnowledgeDocumentsPage").then((module) => ({
    default: module.KnowledgeDocumentsPage,
  })),
);
const KnowledgeDocumentDetailPage = lazy(() =>
  import("@/features/admin/KnowledgeDocumentDetailPage").then((module) => ({
    default: module.KnowledgeDocumentDetailPage,
  })),
);
const KnowledgeRetrievalPage = lazy(() =>
  import("@/features/admin/KnowledgeRetrievalPage").then((module) => ({
    default: module.KnowledgeRetrievalPage,
  })),
);
const SchedulesPage = lazy(() =>
  import("@/features/admin/SchedulesPage").then((module) => ({ default: module.SchedulesPage })),
);
const GroupsPage = lazy(() =>
  import("@/features/admin/GroupsPage").then((module) => ({ default: module.GroupsPage })),
);
const RolesPage = lazy(() =>
  import("@/features/admin/RolesPage").then((module) => ({ default: module.RolesPage })),
);
const TenantsPage = lazy(() =>
  import("@/features/admin/TenantsPage").then((module) => ({ default: module.TenantsPage })),
);
const UsersPage = lazy(() =>
  import("@/features/admin/UsersPage").then((module) => ({ default: module.UsersPage })),
);
const ChangePasswordPage = lazy(() =>
  import("@/features/auth/ChangePasswordPage").then((module) => ({
    default: module.ChangePasswordPage,
  })),
);
const LoginPanel = lazy(() =>
  import("@/features/auth/LoginPanel").then((module) => ({ default: module.LoginPanel })),
);
const AgentDetailPage = lazy(() =>
  import("@/features/public-agents/AgentDetailPage").then((module) => ({
    default: module.AgentDetailPage,
  })),
);
const AgentDirectoryPage = lazy(() =>
  import("@/features/public-agents/AgentDirectoryPage").then((module) => ({
    default: module.AgentDirectoryPage,
  })),
);
const ChatPage = lazy(() =>
  import("@/features/ai-chat/ChatPage").then((module) => ({ default: module.ChatPage })),
);

export function App() {
  return (
    <Suspense
      fallback={
        <div className="center-state">
          <Spin size="large" />
        </div>
      }
    >
      <Routes>
        <Route element={<PublicLayout />}>
          <Route index element={<AgentDirectoryPage />} />
          <Route path="agents/:slug" element={<AgentDetailPage />} />
          <Route path="im/websocket/:channelKey" element={<ChatPage />} />
        </Route>
        <Route path="admin/login" element={<LoginPanel />} />
        <Route path="admin" element={<RequireAuth />}>
          <Route path="change-password" element={<ChangePasswordPage />} />
          <Route element={<RequirePasswordChanged />}>
            <Route element={<AdminLayout />}>
              <Route index element={<AdminDashboard />} />
              <Route element={<RequirePermission permission="platform.tenants.manage" />}>
                <Route path="tenants" element={<TenantsPage />} />
              </Route>
              <Route element={<RequirePermission permission="tenant.users.read" />}>
                <Route path="users" element={<UsersPage />} />
              </Route>
              <Route element={<RequirePermission permission="tenant.groups.read" />}>
                <Route path="groups" element={<GroupsPage />} />
              </Route>
              <Route element={<RequirePermission permission="tenant.roles.read" />}>
                <Route path="roles" element={<RolesPage />} />
              </Route>
              <Route element={<RequirePermission permission="agents.read" />}>
                <Route path="agents" element={<AgentsPage />} />
                <Route path="agents/:agentId" element={<AgentWorkspacePage />} />
              </Route>
              <Route element={<RequirePermission permission="llm_configs.read" />}>
                <Route path="llm-configs" element={<LlmConfigsPage />} />
              </Route>
              <Route element={<RequirePermission permission="skills.read" />}>
                <Route path="skills" element={<SkillsPage />} />
                <Route path="skills/:skillId" element={<SkillDetailPage />} />
              </Route>
              <Route element={<RequirePermission permission="skills.manage" />}>
                <Route path="skills/:skillId/edit" element={<SkillEditorPage />} />
              </Route>
              <Route element={<RequirePermission permission="mcp_servers.read" />}>
                <Route path="mcp-servers" element={<McpServersPage />} />
              </Route>
              <Route element={<RequirePermission permission="interactions.read.any" />}>
                <Route path="runs" element={<RunsPage />} />
                <Route path="runs/requesters/:actorType/:actorId" element={<RequesterRunsPage />} />
                <Route path="runs/:runId" element={<Navigate replace to="/admin/runs" />} />
              </Route>
              <Route element={<RequirePermission permission="memory.read" />}>
                <Route path="memory" element={<MemoryPage />} />
              </Route>
              <Route element={<RequirePermission permission="knowledge.spaces.read" />}>
                <Route path="knowledge" element={<KnowledgePage />} />
                <Route element={<RequirePermission permission="knowledge.spaces.manage" />}>
                  <Route path="knowledge/new" element={<KnowledgeSpaceCreatePage />} />
                </Route>
                <Route path="knowledge/:spaceId/documents" element={<KnowledgeDocumentsPage />} />
                <Route
                  path="knowledge/:spaceId/documents/:documentId"
                  element={<KnowledgeDocumentDetailPage />}
                />
                <Route element={<RequirePermission permission="knowledge.query" />}>
                  <Route path="knowledge/:spaceId/retrieval" element={<KnowledgeRetrievalPage />} />
                </Route>
              </Route>
              <Route element={<RequirePermission permission="schedules.read" />}>
                <Route path="schedules" element={<SchedulesPage />} />
              </Route>
              <Route element={<RequirePermission permission="audit.read" />}>
                <Route path="audit" element={<AuditPage />} />
              </Route>
            </Route>
          </Route>
        </Route>
        <Route path="404" element={<NotFoundPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
