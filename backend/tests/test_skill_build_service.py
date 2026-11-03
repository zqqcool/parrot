from datetime import UTC, datetime

from app.modules.skills.build_service import skill_build_view
from app.modules.skills.models import SkillBuildJob, SkillVersion


def test_build_view_exposes_a_reviewed_failure_message() -> None:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    job = SkillBuildJob(
        id="skill_build_test",
        tenant_id="tenant_test",
        skill_version_id="skill_version_test",
        source_checksum="a" * 64,
        status="failed",
        error_code="SKILL_SANDBOX_UNAVAILABLE",
        created_at=now,
        updated_at=now,
    )
    version = SkillVersion(
        id="skill_version_test",
        tenant_id="tenant_test",
        skill_id="skill_test",
        version=1,
        status="draft",
        created_at=now,
        updated_at=now,
    )

    view = skill_build_view(job, version)

    assert view.error_code == "SKILL_SANDBOX_UNAVAILABLE"
    assert view.failure_message == (
        "Skill 构建沙箱不可用，请联系管理员启用受支持的 Linux TaskIQ 构建 worker。"
    )
