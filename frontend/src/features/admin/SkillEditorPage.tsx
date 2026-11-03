import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Result } from "antd";
import { useNavigate, useParams } from "react-router-dom";

import { SkillEditorHeader } from "@/features/admin/SkillEditorHeader";
import { SkillEditorWorkspace } from "@/features/admin/SkillEditorWorkspace";
import {
  updateOpenedChecksums,
  withDirtyPath,
  withoutDirtyPath,
  withoutDirtyPathPrefix,
} from "@/features/admin/skillDraftFileState";
import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import type { SkillFileContent } from "@/shared/api/types";
import type { WorkspaceFile } from "@/shared/ui/WorkspaceEditor";
import { WorkspaceLargePreview } from "@/shared/ui/WorkspaceLargePreview";

// This page coordinates the editor's independent query and mutation states.
// eslint-disable-next-line complexity
export function SkillEditorPage() {
  const { skillId = "" } = useParams();
  const tenantId = useTenantId();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [activePath, setActivePath] = useState<string | null>(null);
  const [opened, setOpened] = useState<Record<string, SkillFileContent>>({});
  const [dirtyPaths, setDirtyPaths] = useState<Set<string>>(() => new Set());
  const [draftChecksum, setDraftChecksum] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);
  const skillsQuery = useQuery({
    queryKey: ["admin", tenantId, "skills"],
    queryFn: () => adminApi.listSkills(tenantId ?? ""),
    enabled: Boolean(tenantId),
  });
  const skill = skillsQuery.data?.find((item) => item.id === skillId);
  const versionsQuery = useQuery({
    queryKey: ["admin", tenantId, "skills", skillId, "versions"],
    queryFn: () => adminApi.listSkillVersions(tenantId ?? "", skillId),
    enabled: Boolean(tenantId && skill),
  });
  const draft = versionsQuery.data?.find((version) => version.status === "draft");
  const filesQuery = useQuery({
    queryKey: ["admin", tenantId, "skills", skillId, "versions", draft?.id, "files"],
    queryFn: () => adminApi.listSkillVersionFiles(tenantId ?? "", skillId, draft?.id ?? ""),
    enabled: Boolean(tenantId && draft),
  });
  const loadFile = useMutation({
    mutationFn: (path: string) =>
      adminApi.getSkillVersionFile(tenantId ?? "", skillId, draft?.id ?? "", path),
    onSuccess: (file) => setOpened((current) => ({ ...current, [file.path]: file })),
  });
  const save = useMutation({
    mutationFn: (path: string) => {
      const file = opened[path];
      if (!file) throw new Error("未加载文件内容");
      return adminApi.writeSkillDraftFile(tenantId ?? "", skillId, path, {
        content: file.content,
        expected_checksum: file.checksum,
      });
    },
    onSuccess: async (file) => {
      setOpened((current) =>
        Object.fromEntries(
          Object.entries(current).map(([path, openedFile]) => [
            path,
            path === file.path ? file : { ...openedFile, checksum: file.checksum },
          ]),
        ),
      );
      setDraftChecksum(file.checksum);
      await client.invalidateQueries({
        queryKey: ["admin", tenantId, "skills", skillId, "versions", draft?.id, "files"],
      });
      await client.invalidateQueries({
        queryKey: ["admin", tenantId, "skills", skillId, "versions"],
      });
      setDirtyPaths((current) => withoutDirtyPath(current, file.path));
    },
  });
  const entries = useMutation({
    mutationFn: async ({
      action,
      path,
      content,
    }: {
      action: "file" | "directory" | "delete";
      path: string;
      content?: string;
    }) => {
      const expectedChecksum = draftChecksum || draft?.package_sha256;
      if (!expectedChecksum) throw new Error("草稿校验和不可用，请刷新后重试");
      if (action === "file") {
        return adminApi.createSkillDraftFile(tenantId ?? "", skillId, {
          path,
          content: content ?? "",
          expected_checksum: expectedChecksum,
        });
      }
      if (action === "directory") {
        return adminApi.createSkillDraftDirectory(tenantId ?? "", skillId, {
          path,
          expected_checksum: expectedChecksum,
        });
      }
      return adminApi.deleteSkillDraftEntry(tenantId ?? "", skillId, {
        path,
        expected_checksum: expectedChecksum,
      });
    },
    onSuccess: async (result) => {
      setDraftChecksum(result.checksum);
      setOpened((current) => updateOpenedChecksums(current, result.checksum));
      await client.invalidateQueries({
        queryKey: ["admin", tenantId, "skills", skillId, "versions", draft?.id, "files"],
      });
      await client.invalidateQueries({
        queryKey: ["admin", tenantId, "skills", skillId, "versions"],
      });
    },
  });
  const publish = useMutation({
    mutationFn: () => adminApi.publishSkill(tenantId ?? "", skillId),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "skills"] });
      void navigate(`/admin/skills/${skillId}`);
    },
  });

  useEffect(() => {
    setOpened({});
    setDirtyPaths(new Set());
  }, [draft?.id]);
  useEffect(() => {
    setDraftChecksum(draft?.package_sha256 ?? "");
  }, [draft?.package_sha256]);
  const workspaceFiles = useMemo<WorkspaceFile[]>(
    () => (filesQuery.data ?? []).map((file) => ({ ...file, content: opened[file.path]?.content })),
    [filesQuery.data, opened],
  );
  const activeFile = activePath ? opened[activePath] : undefined;
  if (!tenantId) return <Result status="404" title="请先选择租户" />;
  if (skillsQuery.isPending || versionsQuery.isPending)
    return <Result status="info" title="正在加载 Skill" />;
  if (!skill) return <Result status="404" title="Skill 不存在或无权查看" />;
  if (!draft) {
    return (
      <Result
        extra={<Button onClick={() => void navigate(`/admin/skills/${skillId}`)}>选择版本</Button>}
        status="info"
        title="尚未创建可编辑草稿"
      />
    );
  }
  const hasManifest = (filesQuery.data ?? []).some((item) => item.path === "manifest.json");
  const publishDisabled = dirtyPaths.size > 0;
  return (
    <section className="skill-editor-page">
      <SkillEditorHeader
        draft={draft}
        entryLoading={entries.isPending}
        hasManifest={hasManifest}
        publishLoading={publish.isPending}
        publishDisabled={publishDisabled}
        skill={skill}
        skillId={skillId}
        onCreateManifest={() =>
          entries.mutate(
            {
              action: "file",
              path: "manifest.json",
              content: '{"execute":false}\n',
            },
            { onSuccess: () => loadFile.mutate("manifest.json") },
          )
        }
        onPublish={() => publish.mutate()}
      />
      <SkillEditorWorkspace
        activePath={activePath}
        activeFile={activeFile}
        files={workspaceFiles}
        filePaths={(filesQuery.data ?? []).map((item) => item.path)}
        loadingPath={loadFile.isPending ? activePath : null}
        operationPending={entries.isPending}
        refreshingFiles={filesQuery.isFetching}
        saveDisabled={!activeFile?.editable || !dirtyPaths.has(activeFile.path)}
        saveLoading={save.isPending}
        onOpen={(path) => {
          setActivePath(path);
          if (!opened[path]) loadFile.mutate(path);
        }}
        onPreview={() => setPreviewOpen(true)}
        onSave={(path) => save.mutate(path)}
        onCreateFile={async (path) => {
          await entries.mutateAsync({ action: "file", path });
          setActivePath(path);
          loadFile.mutate(path);
        }}
        onCreateDirectory={async (path) => {
          await entries.mutateAsync({ action: "directory", path });
        }}
        onDelete={async (path) => {
          await entries.mutateAsync({ action: "delete", path });
          if (activePath === path || activePath?.startsWith(`${path}/`)) setActivePath(null);
          setOpened((current) =>
            Object.fromEntries(
              Object.entries(current).filter(
                ([openedPath]) => openedPath !== path && !openedPath.startsWith(`${path}/`),
              ),
            ),
          );
          setDirtyPaths((current) => withoutDirtyPathPrefix(current, path));
        }}
        onRefresh={() => void filesQuery.refetch()}
        onChange={(path, content) => {
          if (opened[path]?.content === content) return;
          setOpened((current) => {
            const file = current[path];
            return file ? { ...current, [path]: { ...file, content } } : current;
          });
          setDirtyPaths((current) => withDirtyPath(current, path));
        }}
      />
      <WorkspaceLargePreview
        file={activeFile}
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
      />
    </section>
  );
}
