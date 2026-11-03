from __future__ import annotations

from pydantic import BaseModel


class DashboardMetric(BaseModel):
    value: int | None
    supported: bool = True


class DashboardServiceStatus(BaseModel):
    health: str
    database: str
    redis: str
    runtime: str
    environment: str


class DashboardOverview(BaseModel):
    agents: DashboardMetric
    llm_configs: DashboardMetric
    skills: DashboardMetric
    mcp_servers: DashboardMetric
    im_entries: DashboardMetric
    runs: DashboardMetric
    active_runs: int
    service: DashboardServiceStatus
    dependency_warnings: tuple[str, ...]
