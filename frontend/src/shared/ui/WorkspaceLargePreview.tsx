import Editor from "@monaco-editor/react";
import { Empty, Modal } from "antd";

import "@/shared/ui/monaco";
import "@/shared/ui/workspace-large-preview.css";
import { MarkdownPreview } from "@/shared/ui/MarkdownPreview";
import { isWorkspaceMarkdown, workspaceLanguageFor } from "@/shared/ui/workspace-language";

export type WorkspacePreviewFile = {
  path: string;
  content?: string;
};

type Props = {
  file?: WorkspacePreviewFile;
  open: boolean;
  onClose: () => void;
};

export function WorkspaceLargePreview({ file, open, onClose }: Props) {
  return (
    <Modal
      className="workspace-large-preview"
      destroyOnHidden
      footer={null}
      open={open}
      title={null}
      width="100vw"
      onCancel={onClose}
    >
      <PreviewContent file={file} />
    </Modal>
  );
}

function PreviewContent({ file }: Pick<Props, "file">) {
  if (!file || file.content === undefined)
    return (
      <div className="workspace-large-preview__empty">
        <Empty description="请先从文件树中选择已加载的文件" />
      </div>
    );
  if (isWorkspaceMarkdown(file.path))
    return <MarkdownPreview className="workspace-large-preview__markdown" value={file.content} />;
  return (
    <div className="workspace-large-preview__code">
      <Editor
        height="100%"
        language={workspaceLanguageFor(file.path)}
        options={{
          automaticLayout: true,
          fontSize: 14,
          minimap: { enabled: false },
          readOnly: true,
          scrollBeyondLastLine: false,
          wordWrap: "on",
        }}
        path={`preview:${file.path}`}
        theme="vs"
        value={file.content}
      />
    </div>
  );
}
