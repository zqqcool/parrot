import Editor from "@monaco-editor/react";
import { Button, Empty, Segmented, Space, Splitter, Spin, Tabs, Tooltip } from "antd";
import { useState } from "react";
import type { ReactNode } from "react";

import "@/shared/ui/monaco";
import "@/shared/ui/workspace-editor.css";
import { MarkdownPreview } from "@/shared/ui/MarkdownPreview";
import { WorkspaceFileTree } from "@/shared/ui/WorkspaceFileTree";
import { isWorkspaceMarkdown, workspaceLanguageFor } from "@/shared/ui/workspace-language";
import { AppIcon } from "@/shared/icons";

export type WorkspaceFile = {
  path: string;
  content?: string;
  editable: boolean;
  kind?: string;
};

type Props = {
  activePath: string | null;
  files: WorkspaceFile[];
  loadingPath?: string | null;
  onChange: (path: string, content: string) => void;
  onOpen: (path: string) => void;
  onSave?: (path: string) => void;
  saveDisabled?: boolean;
  saveLoading?: boolean;
  operationPending?: boolean;
  previewDisabled?: boolean;
  refreshingFiles?: boolean;
  onCreateFile?: (path: string) => Promise<void>;
  onCreateDirectory?: (path: string) => Promise<void>;
  onDelete?: (path: string) => Promise<void>;
  onRefresh?: () => void;
  renderEditor?: (file: WorkspaceFile, onChange: (content: string) => void) => ReactNode;
  onPreview?: () => void;
};

type MarkdownMode = "edit" | "preview";

export function WorkspaceEditor({
  activePath,
  files,
  loadingPath,
  onChange,
  onOpen,
  onSave,
  saveDisabled,
  saveLoading,
  operationPending,
  previewDisabled,
  refreshingFiles,
  onCreateFile,
  onCreateDirectory,
  onDelete,
  onRefresh,
  renderEditor,
  onPreview,
}: Props) {
  const [markdownMode, setMarkdownMode] = useState<MarkdownMode>("edit");
  const activeFile = files.find((file) => file.path === activePath);
  const openedFiles = files.filter((file) => file.content !== undefined);
  const isMarkdown = isWorkspaceMarkdown(activeFile?.path);

  return (
    <section className="workspace-editor" aria-label="文件编辑器">
      <Splitter className="workspace-editor__splitter">
        <Splitter.Panel defaultSize={280} max="35%" min={240}>
          <WorkspaceFileTree
            activePath={activePath}
            files={files}
            operationPending={operationPending}
            refreshing={refreshingFiles}
            onCreateDirectory={onCreateDirectory}
            onCreateFile={onCreateFile}
            onDelete={onDelete}
            onOpen={onOpen}
            onRefresh={onRefresh}
          />
        </Splitter.Panel>
        <Splitter.Panel>
          <div className="workspace-editor__main">
            <WorkspaceTabs
              activePath={activePath}
              files={openedFiles}
              markdownMode={markdownMode}
              showMarkdownMode={isMarkdown}
              previewDisabled={previewDisabled}
              onMarkdownModeChange={setMarkdownMode}
              onOpen={onOpen}
              onPreview={onPreview}
            />
            <WorkspaceEditorPane
              activeFile={activeFile}
              loadingPath={loadingPath}
              preview={isMarkdown && markdownMode === "preview"}
              onChange={onChange}
              renderEditor={renderEditor}
            />
            <WorkspaceFooter
              activeFile={activeFile}
              onSave={onSave}
              saveDisabled={saveDisabled}
              saveLoading={saveLoading}
            />
          </div>
        </Splitter.Panel>
      </Splitter>
    </section>
  );
}

function WorkspaceTabs({
  activePath,
  files,
  markdownMode,
  showMarkdownMode,
  previewDisabled,
  onMarkdownModeChange,
  onOpen,
  onPreview,
}: Pick<Props, "activePath" | "onOpen"> & {
  files: WorkspaceFile[];
  markdownMode: MarkdownMode;
  previewDisabled?: boolean;
  showMarkdownMode: boolean;
  onMarkdownModeChange: (mode: MarkdownMode) => void;
  onPreview?: () => void;
}) {
  return (
    <Tabs
      activeKey={activePath ?? undefined}
      className="workspace-editor__tabs"
      hideAdd
      items={files.map((file) => ({ key: file.path, label: file.path.split("/").pop() }))}
      tabBarExtraContent={
        <Space size={8}>
          {showMarkdownMode ? (
            <Segmented
              aria-label="Markdown 显示模式"
              options={[
                { label: "编辑", value: "edit" },
                { label: "预览", value: "preview" },
              ]}
              size="small"
              value={markdownMode}
              onChange={(value) => onMarkdownModeChange(value === "preview" ? "preview" : "edit")}
            />
          ) : null}
          {onPreview ? (
            <Tooltip title={previewDisabled ? "请先选择一个已加载文件" : "大屏预览当前文件"}>
              <Button
                aria-label="大屏预览"
                disabled={previewDisabled}
                icon={<AppIcon name="FullScreenOne" size="md" />}
                size="small"
                type="text"
                onClick={onPreview}
              >
                大屏预览
              </Button>
            </Tooltip>
          ) : null}
        </Space>
      }
      onChange={onOpen}
    />
  );
}

function WorkspaceEditorPane({
  activeFile,
  loadingPath,
  preview,
  onChange,
  renderEditor,
}: Pick<Props, "loadingPath" | "onChange"> & {
  activeFile: WorkspaceFile | undefined;
  preview: boolean;
  renderEditor?: Props["renderEditor"];
}) {
  if (!activeFile)
    return (
      <div className="workspace-editor__content">
        <Empty description="从左侧选择文件" />
      </div>
    );
  if (loadingPath === activeFile.path)
    return (
      <div className="workspace-editor__content">
        <Spin size="large" />
      </div>
    );
  const customEditor =
    activeFile.content !== undefined && renderEditor
      ? renderEditor(activeFile, (content) => onChange(activeFile.path, content))
      : null;
  return (
    <div
      className={
        customEditor
          ? "workspace-editor__content workspace-editor__content--custom"
          : "workspace-editor__content"
      }
    >
      {customEditor ??
        (preview && activeFile.content !== undefined ? (
          <MarkdownPreview value={activeFile.content} />
        ) : activeFile.content !== undefined ? (
          <Editor
            height="100%"
            language={workspaceLanguageFor(activeFile.path)}
            options={editorOptions(activeFile.editable)}
            path={activeFile.path}
            theme="vs"
            value={activeFile.content}
            onChange={(content) => onChange(activeFile.path, content ?? "")}
          />
        ) : null)}
    </div>
  );
}

function WorkspaceFooter({
  activeFile,
  onSave,
  saveDisabled,
  saveLoading,
}: Pick<Props, "onSave" | "saveDisabled" | "saveLoading"> & {
  activeFile: WorkspaceFile | undefined;
}) {
  return (
    <footer>
      <span>{activeFile?.editable ? "草稿文件" : "此文件不可编辑"}</span>
      {onSave && activeFile?.editable ? (
        <Button
          disabled={saveDisabled}
          loading={saveLoading}
          type="primary"
          onClick={() => onSave(activeFile.path)}
        >
          保存
        </Button>
      ) : null}
    </footer>
  );
}

function editorOptions(editable: boolean) {
  return {
    automaticLayout: true,
    fontSize: 13,
    minimap: { enabled: false },
    readOnly: !editable,
    scrollBeyondLastLine: false,
    wordWrap: "on" as const,
  };
}
