import { Button, Space } from "antd";
import { Link } from "react-router-dom";

import type { Skill, SkillVersion } from "@/shared/api/types";
import { AdminPageHeader } from "@/shared/ui";

type SkillEditorHeaderProps = {
  draft: Pick<SkillVersion, "source_version_id" | "version">;
  entryLoading: boolean;
  hasManifest: boolean;
  publishLoading: boolean;
  publishDisabled: boolean;
  skill: Pick<Skill, "name">;
  skillId: string;
  onCreateManifest: () => void;
  onPublish: () => void;
};

export function SkillEditorHeader({
  draft,
  entryLoading,
  hasManifest,
  publishLoading,
  publishDisabled,
  skill,
  skillId,
  onCreateManifest,
  onPublish,
}: SkillEditorHeaderProps) {
  return (
    <AdminPageHeader
      action={
        <Space wrap>
          {!hasManifest ? (
            <Button loading={entryLoading} onClick={onCreateManifest}>
              创建 manifest.json
            </Button>
          ) : null}
          <Button
            disabled={publishDisabled}
            loading={publishLoading}
            type="primary"
            onClick={onPublish}
          >
            发布草稿
          </Button>
        </Space>
      }
      breadcrumbs={[
        { title: <Link to="/admin">工作台</Link> },
        { title: <Link to="/admin/skills">Skill 管理</Link> },
        { title: <Link to={`/admin/skills/${skillId}`}>{skill.name}</Link> },
        { title: "文件编辑" },
      ]}
      compact
      description={`草稿 v${draft.version}，来源：${draft.source_version_id ? "历史版本" : "导入文件包"}`}
      title={`${skill.name} · 文件编辑`}
    />
  );
}
