import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Modal, Select, Space, Upload } from "antd";
import type { UploadFile } from "antd";
import { useNavigate } from "react-router-dom";

import { SkillCards } from "@/features/admin/SkillCards";
import { SkillRecallModal } from "@/features/admin/SkillRecallModal";
import { filterSkills, type SkillStatusFilter } from "@/features/admin/skillFilters";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import { useAuth } from "@/shared/auth/useAuth";
import { AppIcon } from "@/shared/icons";
import { RequestErrorAlert, SearchBar, useDebouncedValue } from "@/shared/ui";

const statusOptions = [
  { value: "all", label: "全部状态" },
  { value: "published", label: "已发布" },
  { value: "draft", label: "草稿" },
  { value: "disabled", label: "已停用" },
] satisfies { value: SkillStatusFilter; label: string }[];

export function SkillsPage() {
  const tenantId = useTenantId();
  const client = useQueryClient();
  const auth = useAuth();
  const navigate = useNavigate();
  const [importOpen, setImportOpen] = useState(false);
  const [recallOpen, setRecallOpen] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const [statusFilter, setStatusFilter] = useState<SkillStatusFilter>("all");
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const query = useQuery({
    queryKey: ["admin", tenantId, "skills", searchQuery],
    queryFn: () => adminApi.listSkills(tenantId ?? "", searchQuery),
    enabled: Boolean(tenantId),
  });
  const importSkill = useMutation({
    mutationFn: (file: File) => adminApi.importSkill(tenantId ?? "", file),
    onSuccess: async () => {
      setImportOpen(false);
      setFileList([]);
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "skills"] });
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "dashboard"] });
    },
  });
  const publish = useMutation({
    mutationFn: (skillId: string) => adminApi.publishSkill(tenantId ?? "", skillId),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "skills"] });
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "dashboard"] });
    },
  });
  if (!tenantId) return <TenantRequiredState />;

  const skills = query.data ?? [];
  const filteredSkills = filterSkills(skills, statusFilter);
  const resetFilters = () => {
    setSearchValue("");
    setStatusFilter("all");
  };

  return (
    <section className="skills-page">
      <h1 className="skills-page-title">Skill 管理</h1>
      <SearchBar
        actions={
          <Space>
            {auth.hasPermission("agents.read") ? (
              <Button
                color="primary"
                icon={<AppIcon name="Search" size="md" />}
                variant="outlined"
                onClick={() => setRecallOpen(true)}
              >
                召回验证
              </Button>
            ) : null}
            {auth.hasPermission("skills.manage") ? (
              <Button
                icon={<AppIcon name="Upload" size="md" />}
                type="primary"
                onClick={() => setImportOpen(true)}
              >
                导入 Skill
              </Button>
            ) : null}
          </Space>
        }
        advancedFilters={
          <Select
            aria-label="按状态筛选 Skill"
            options={statusOptions}
            value={statusFilter}
            onChange={setStatusFilter}
          />
        }
        hasActiveFilters={statusFilter !== "all"}
        placeholder="按名称或描述搜索"
        value={searchValue}
        onChange={setSearchValue}
        onReset={resetFilters}
      />

      <dl className="skills-summary" aria-label="Skill 统计">
        <SkillMetric label={searchQuery ? "匹配 Skill" : "总 Skill"} value={skills.length} />
        <SkillMetric label="本页" value={filteredSkills.length} />
        <SkillMetric
          label="已发布"
          value={skills.filter((skill) => skill.status === "published").length}
        />
        <SkillMetric
          label="仅草稿"
          value={skills.filter((skill) => skill.status === "draft").length}
        />
        <SkillMetric label="有草稿" value={skills.filter((skill) => skill.has_draft).length} />
        <SkillMetric
          label="已停用"
          value={skills.filter((skill) => skill.status === "disabled").length}
        />
      </dl>

      <RequestErrorAlert error={query.error} fallback="加载 Skill 失败" />
      <SkillCards
        canManage={auth.hasPermission("skills.manage")}
        onPublish={(skill) => publish.mutate(skill.id)}
        onView={(skill) => void navigate(`/admin/skills/${skill.id}`)}
        publishPending={publish.isPending}
        skills={filteredSkills}
        loading={query.isFetching}
      />
      <RequestErrorAlert error={publish.error} fallback="发布 Skill 失败" />
      <SkillRecallModal
        canManageAgent={auth.hasPermission("agents.manage")}
        open={recallOpen}
        tenantId={tenantId}
        onClose={() => setRecallOpen(false)}
      />
      <Modal
        title="导入 Skill"
        open={importOpen}
        confirmLoading={importSkill.isPending}
        okButtonProps={{ disabled: !fileList[0]?.originFileObj }}
        onCancel={() => {
          setImportOpen(false);
          setFileList([]);
        }}
        onOk={() => {
          const file = fileList[0]?.originFileObj;
          if (file) importSkill.mutate(file);
        }}
      >
        <RequestErrorAlert error={importSkill.error} fallback="导入 Skill 失败" />
        <Alert
          description="ZIP 根目录（或唯一一级目录）必须包含 SKILL.md。名称和说明从其中的 frontmatter 读取；可同时携带脚本与参考文件。"
          message="导入 Skill ZIP"
          showIcon
          type="info"
        />
        <Upload.Dragger
          accept=".zip,application/zip"
          beforeUpload={() => false}
          fileList={fileList}
          maxCount={1}
          onChange={({ fileList: files }) => setFileList(files.slice(-1))}
        >
          <p className="ant-upload-drag-icon">
            <AppIcon name="Upload" size="xl" />
          </p>
          <p className="ant-upload-text">点击或拖拽 ZIP 文件到此处</p>
          <p className="ant-upload-hint">仅接受 .zip，最大 50 MB。</p>
        </Upload.Dragger>
      </Modal>
    </section>
  );
}

function SkillMetric({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
