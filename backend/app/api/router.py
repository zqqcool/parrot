from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    admin_access,
    admin_agents,
    admin_audit,
    admin_dashboard,
    admin_im,
    admin_knowledge,
    admin_knowledge_documents,
    admin_knowledge_merge,
    admin_llm_configs,
    admin_mcp_servers,
    admin_memory,
    admin_model_configs,
    admin_runs,
    admin_schedules,
    admin_skills,
    admin_tenants,
    admin_users,
    auth,
    health,
    im,
    im_knowledge_media,
    im_websocket,
    public_agents,
)


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(health.router, tags=["health"])
    router.include_router(auth.router, prefix="/auth", tags=["auth"])
    router.include_router(admin_tenants.router, prefix="/admin", tags=["admin-tenants"])
    router.include_router(admin_users.router, prefix="/admin", tags=["admin-users"])
    router.include_router(admin_access.router, prefix="/admin", tags=["admin-access"])
    router.include_router(admin_agents.router, prefix="/admin", tags=["admin-agents"])
    router.include_router(admin_audit.router, prefix="/admin", tags=["admin-audit"])
    router.include_router(admin_dashboard.router, prefix="/admin", tags=["admin-dashboard"])
    router.include_router(admin_llm_configs.router, prefix="/admin", tags=["admin-llm-configs"])
    router.include_router(admin_model_configs.router, prefix="/admin", tags=["admin-model-configs"])
    router.include_router(admin_skills.router, prefix="/admin", tags=["admin-skills"])
    router.include_router(admin_mcp_servers.router, prefix="/admin", tags=["admin-mcp-servers"])
    router.include_router(admin_runs.router, prefix="/admin", tags=["admin-runs"])
    router.include_router(admin_memory.router, prefix="/admin", tags=["admin-memory"])
    router.include_router(admin_knowledge.router, prefix="/admin", tags=["admin-knowledge"])
    router.include_router(admin_knowledge_merge.router, prefix="/admin", tags=["admin-knowledge"])
    router.include_router(
        admin_knowledge_documents.router, prefix="/admin", tags=["admin-knowledge"]
    )
    router.include_router(admin_im.router, prefix="/admin", tags=["admin-im"])
    router.include_router(admin_schedules.router, prefix="/admin", tags=["admin-schedules"])
    router.include_router(public_agents.router, prefix="/public", tags=["public-agents"])
    router.include_router(im.router, prefix="/im", tags=["im"])
    router.include_router(im_knowledge_media.router, prefix="/im", tags=["im"])
    router.include_router(im_websocket.router, prefix="/im", tags=["im"])
    return router
