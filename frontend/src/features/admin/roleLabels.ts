import type { Role } from "@/shared/api/types";

const systemRoleNames: Record<string, string> = {
  agent_manager: "智能体管理员",
  platform_admin: "平台管理员",
  tenant_admin: "租户管理员",
  viewer: "只读成员",
};

export function getRoleDisplayName(role: Role): string {
  if (!role.is_system) return role.name;
  return systemRoleNames[role.key] ?? role.name;
}
