from __future__ import annotations

PLATFORM_TENANTS_MANAGE = "platform.tenants.manage"
TENANT_USERS_READ = "tenant.users.read"
TENANT_USERS_MANAGE = "tenant.users.manage"
TENANT_GROUPS_READ = "tenant.groups.read"
TENANT_GROUPS_MANAGE = "tenant.groups.manage"
TENANT_ROLES_READ = "tenant.roles.read"
TENANT_ROLES_MANAGE = "tenant.roles.manage"
AGENTS_READ = "agents.read"
AGENTS_MANAGE = "agents.manage"
AGENTS_PUBLISH = "agents.publish"
AGENTS_INTERACT = "agents.interact"
LLM_CONFIGS_READ = "llm_configs.read"
LLM_CONFIGS_MANAGE = "llm_configs.manage"
SKILLS_READ = "skills.read"
SKILLS_MANAGE = "skills.manage"
MCP_SERVERS_READ = "mcp_servers.read"
MCP_SERVERS_MANAGE = "mcp_servers.manage"
INTERACTIONS_READ_OWN = "interactions.read.own"
INTERACTIONS_READ_ANY = "interactions.read.any"
MEMORY_READ = "memory.read"
MEMORY_MANAGE = "memory.manage"
SCHEDULES_READ = "schedules.read"
SCHEDULES_MANAGE = "schedules.manage"
AUDIT_READ = "audit.read"
IM_CHANNELS_READ = "im.channels.read"
IM_CHANNELS_MANAGE = "im.channels.manage"
KNOWLEDGE_QUERY = "knowledge.query"
KNOWLEDGE_SPACES_READ = "knowledge.spaces.read"
KNOWLEDGE_SPACES_MANAGE = "knowledge.spaces.manage"
KNOWLEDGE_DOCUMENTS_READ = "knowledge.documents.read"
KNOWLEDGE_DOCUMENTS_MANAGE = "knowledge.documents.manage"
KNOWLEDGE_ACCESS_MANAGE = "knowledge.access.manage"


PERMISSION_CATALOG: dict[str, str] = {
    PLATFORM_TENANTS_MANAGE: "管理平台租户",
    TENANT_USERS_READ: "查看当前租户用户",
    TENANT_USERS_MANAGE: "创建和管理当前租户用户",
    TENANT_GROUPS_READ: "查看当前租户用户组",
    TENANT_GROUPS_MANAGE: "创建和管理当前租户用户组",
    TENANT_ROLES_READ: "查看当前租户角色与权限",
    TENANT_ROLES_MANAGE: "创建和管理当前租户角色",
    AGENTS_READ: "查看当前租户智能体配置",
    AGENTS_MANAGE: "创建和更新当前租户智能体",
    AGENTS_PUBLISH: "发布智能体并配置匿名访问",
    AGENTS_INTERACT: "与当前租户智能体交互",
    LLM_CONFIGS_READ: "查看当前租户 LLM 配置",
    LLM_CONFIGS_MANAGE: "创建和更新当前租户 LLM 配置",
    SKILLS_READ: "查看当前租户 Skill",
    SKILLS_MANAGE: "创建、版本管理和发布当前租户 Skill",
    MCP_SERVERS_READ: "查看当前租户 MCP 服务配置",
    MCP_SERVERS_MANAGE: "创建和更新当前租户 MCP 服务配置",
    INTERACTIONS_READ_OWN: "查看本人发起的交互记录",
    INTERACTIONS_READ_ANY: "查看当前租户全部交互记录",
    MEMORY_READ: "查看当前租户记忆记录",
    MEMORY_MANAGE: "创建和管理当前租户记忆记录",
    SCHEDULES_READ: "查看当前租户定时任务",
    SCHEDULES_MANAGE: "创建和管理当前租户定时任务",
    AUDIT_READ: "查看当前租户审计事件",
    IM_CHANNELS_READ: "查看当前租户 IM 渠道配置",
    IM_CHANNELS_MANAGE: "创建和管理当前租户 IM 渠道",
    KNOWLEDGE_QUERY: "在管理台查询获管理授权的知识空间",
    KNOWLEDGE_SPACES_READ: "查看获管理授权的知识空间元数据",
    KNOWLEDGE_SPACES_MANAGE: "创建和管理获授权的知识空间",
    KNOWLEDGE_DOCUMENTS_READ: "查看获管理授权的知识文档",
    KNOWLEDGE_DOCUMENTS_MANAGE: "创建和管理获授权的知识文档",
    KNOWLEDGE_ACCESS_MANAGE: "管理知识空间的用户和用户组访问权限",
}


SYSTEM_ROLES: dict[str, tuple[str, ...]] = {
    "platform_admin": tuple(PERMISSION_CATALOG),
    "tenant_admin": tuple(key for key in PERMISSION_CATALOG if not key.startswith("platform.")),
    "agent_manager": (
        AGENTS_READ,
        AGENTS_MANAGE,
        AGENTS_PUBLISH,
        AGENTS_INTERACT,
        INTERACTIONS_READ_OWN,
        INTERACTIONS_READ_ANY,
        MEMORY_READ,
        MEMORY_MANAGE,
        SCHEDULES_READ,
        SCHEDULES_MANAGE,
        LLM_CONFIGS_READ,
        LLM_CONFIGS_MANAGE,
        SKILLS_READ,
        SKILLS_MANAGE,
        MCP_SERVERS_READ,
        MCP_SERVERS_MANAGE,
        IM_CHANNELS_READ,
        IM_CHANNELS_MANAGE,
        KNOWLEDGE_QUERY,
        KNOWLEDGE_SPACES_READ,
        KNOWLEDGE_SPACES_MANAGE,
        KNOWLEDGE_DOCUMENTS_READ,
        KNOWLEDGE_DOCUMENTS_MANAGE,
        KNOWLEDGE_ACCESS_MANAGE,
    ),
    "viewer": (
        TENANT_USERS_READ,
        TENANT_GROUPS_READ,
        TENANT_ROLES_READ,
        AGENTS_READ,
        LLM_CONFIGS_READ,
        SKILLS_READ,
        MCP_SERVERS_READ,
        INTERACTIONS_READ_OWN,
        MEMORY_READ,
        SCHEDULES_READ,
        KNOWLEDGE_QUERY,
        KNOWLEDGE_SPACES_READ,
        KNOWLEDGE_DOCUMENTS_READ,
    ),
}
