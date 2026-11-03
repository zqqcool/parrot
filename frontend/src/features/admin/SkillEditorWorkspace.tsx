import { SkillManifestForm } from "@/features/admin/SkillManifestForm";
import type { SkillFileContent } from "@/shared/api/types";
import { type WorkspaceFile, WorkspaceEditor } from "@/shared/ui/WorkspaceEditor";

type SkillEditorWorkspaceProps = {
  activeFile: SkillFileContent | undefined;
  activePath: string | null;
  files: WorkspaceFile[];
  filePaths: string[];
  loadingPath: string | null;
  operationPending: boolean;
  refreshingFiles: boolean;
  saveDisabled: boolean;
  saveLoading: boolean;
  onChange: (path: string, content: string) => void;
  onCreateDirectory: (path: string) => Promise<void>;
  onCreateFile: (path: string) => Promise<void>;
  onDelete: (path: string) => Promise<void>;
  onOpen: (path: string) => void;
  onPreview: () => void;
  onRefresh: () => void;
  onSave: (path: string) => void;
};

export function SkillEditorWorkspace({
  activeFile,
  activePath,
  files,
  filePaths,
  loadingPath,
  operationPending,
  refreshingFiles,
  saveDisabled,
  saveLoading,
  onChange,
  onCreateDirectory,
  onCreateFile,
  onDelete,
  onOpen,
  onPreview,
  onRefresh,
  onSave,
}: SkillEditorWorkspaceProps) {
  return (
    <WorkspaceEditor
      activePath={activePath}
      files={files}
      loadingPath={loadingPath}
      operationPending={operationPending}
      previewDisabled={activeFile?.content === undefined}
      refreshingFiles={refreshingFiles}
      saveDisabled={saveDisabled}
      saveLoading={saveLoading}
      onChange={onChange}
      onCreateDirectory={onCreateDirectory}
      onCreateFile={onCreateFile}
      onDelete={onDelete}
      onOpen={onOpen}
      onPreview={onPreview}
      onRefresh={onRefresh}
      onSave={onSave}
      renderEditor={(file, onEditorChange) =>
        file.path === "manifest.json" ? (
          <SkillManifestForm
            availablePaths={filePaths}
            content={file.content ?? "{}"}
            disabled={!file.editable}
            onChange={onEditorChange}
          />
        ) : null
      }
    />
  );
}
