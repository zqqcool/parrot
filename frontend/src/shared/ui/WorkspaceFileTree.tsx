import { Button, Form, Input, Modal, Spin, Tooltip, Tree } from "antd";
import type { DataNode } from "antd/es/tree";
import { useEffect, useMemo, useState } from "react";

import type { WorkspaceFile } from "@/shared/ui/WorkspaceEditor";
import { AppIcon } from "@/shared/icons";

type CreateKind = "file" | "directory";
type TreeNode = DataNode & { entryKind: CreateKind; path: string };

type Props = {
  activePath: string | null;
  files: WorkspaceFile[];
  operationPending?: boolean;
  refreshing?: boolean;
  onCreateDirectory?: (path: string) => Promise<void>;
  onCreateFile?: (path: string) => Promise<void>;
  onDelete?: (path: string) => Promise<void>;
  onOpen: (path: string) => void;
  onRefresh?: () => void;
};

export function WorkspaceFileTree({
  activePath,
  files,
  operationPending,
  refreshing,
  onCreateDirectory,
  onCreateFile,
  onDelete,
  onOpen,
  onRefresh,
}: Props) {
  const [form] = Form.useForm<{ path: string }>();
  const [createKind, setCreateKind] = useState<CreateKind | null>(null);
  const [deletePath, setDeletePath] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState(activePath ? fileKey(activePath) : "");
  const treeData = useMemo(() => toTreeData(files), [files]);
  const canMutate = Boolean(onCreateFile && onCreateDirectory && onDelete);

  useEffect(() => {
    if (activePath) setSelectedKey(fileKey(activePath));
  }, [activePath]);

  const openCreate = (kind: CreateKind) => {
    form.resetFields();
    setCreateKind(kind);
  };
  const create = async () => {
    const { path } = await form.validateFields();
    if (createKind === "file") await onCreateFile?.(path);
    if (createKind === "directory") await onCreateDirectory?.(path);
    setCreateKind(null);
  };
  const remove = async () => {
    if (deletePath) await onDelete?.(deletePath);
    setDeletePath(null);
  };

  return (
    <aside className="workspace-editor__tree">
      <header>
        <span>文件</span>
        <div className="workspace-editor__tree-actions">
          {onRefresh ? (
            <Tooltip title="刷新文件">
              <Button
                aria-label="刷新文件"
                disabled={refreshing}
                icon={<AppIcon name="Refresh" size="sm" />}
                size="small"
                type="text"
                onClick={onRefresh}
              />
            </Tooltip>
          ) : null}
          {canMutate ? (
            <>
              <Tooltip title="新建文件">
                <Button
                  aria-label="新建文件"
                  icon={<AppIcon name="FileAddition" size="sm" />}
                  size="small"
                  type="text"
                  onClick={() => openCreate("file")}
                />
              </Tooltip>
              <Tooltip title="新建目录">
                <Button
                  aria-label="新建目录"
                  icon={<AppIcon name="FolderPlus" size="sm" />}
                  size="small"
                  type="text"
                  onClick={() => openCreate("directory")}
                />
              </Tooltip>
              <Tooltip title="删除所选文件或目录">
                <Button
                  aria-label="删除所选文件或目录"
                  disabled={!selectedKey}
                  icon={<AppIcon name="Delete" size="sm" />}
                  size="small"
                  type="text"
                  onClick={() => setDeletePath(pathFromKey(selectedKey))}
                />
              </Tooltip>
            </>
          ) : null}
        </div>
      </header>
      <Spin spinning={Boolean(refreshing)} tip="正在刷新文件">
        <div aria-busy={refreshing} className="workspace-editor__tree-content">
          <Tree
            blockNode
            defaultExpandAll
            selectedKeys={selectedKey ? [selectedKey] : []}
            treeData={treeData}
            onSelect={(_keys, event) => {
              const node = event.node as TreeNode;
              setSelectedKey(String(node.key));
              if (node.entryKind === "file") onOpen(node.path);
            }}
          />
        </div>
      </Spin>
      <Modal
        confirmLoading={operationPending}
        open={createKind !== null}
        title={createKind === "file" ? "新建文件" : "新建目录"}
        onCancel={() => setCreateKind(null)}
        onOk={() => void create()}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="path"
            label="相对路径"
            rules={[
              { required: true, message: "请输入相对路径" },
              {
                pattern: /^(?!\/)(?!.*(?:^|\/)\.\.?\/)[^\\]+$/,
                message: "路径不能包含 .、.. 或反斜杠",
              },
            ]}
          >
            <Input
              placeholder={createKind === "file" ? "例如：scripts/tool.py" : "例如：references"}
            />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        confirmLoading={operationPending}
        okButtonProps={{ danger: true }}
        okText="删除"
        open={deletePath !== null}
        title="删除文件或目录"
        onCancel={() => setDeletePath(null)}
        onOk={() => void remove()}
      >
        确定删除 <strong>{deletePath}</strong> 吗？删除目录会同时删除其内全部文件，且无法恢复。
      </Modal>
    </aside>
  );
}

function toTreeData(files: WorkspaceFile[]): TreeNode[] {
  const roots: TreeNode[] = [];
  const directories = new Map<string, TreeNode>();
  const ensureDirectory = (path: string): TreeNode => {
    const existing = directories.get(path);
    if (existing) return existing;
    const parentPath = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
    const parent = parentPath ? ensureDirectory(parentPath) : undefined;
    const directory: TreeNode = {
      key: directoryKey(path),
      title: <TreeEntryTitle kind="directory" label={path.split("/").pop() ?? path} />,
      path,
      entryKind: "directory",
      children: [],
    };
    directories.set(path, directory);
    (parent ? (parent.children as TreeNode[]) : roots).push(directory);
    return directory;
  };
  for (const file of files) {
    if (file.kind === "directory") {
      ensureDirectory(file.path);
      continue;
    }
    const parentPath = file.path.includes("/")
      ? file.path.slice(0, file.path.lastIndexOf("/"))
      : "";
    const parent = parentPath ? ensureDirectory(parentPath) : undefined;
    (parent ? (parent.children as TreeNode[]) : roots).push({
      className: parent ? undefined : "workspace-editor__tree-node--root-file",
      key: fileKey(file.path),
      title: <TreeEntryTitle kind="file" label={file.path.split("/").pop() ?? file.path} />,
      path: file.path,
      entryKind: "file",
      isLeaf: true,
    });
  }
  return sortTree(roots);
}

function TreeEntryTitle({ kind, label }: { kind: CreateKind; label: string }) {
  return (
    <span className="workspace-editor__tree-entry" title={label}>
      <AppIcon name={kind === "directory" ? "Folder" : "FileText"} size="sm" />
      <span>{label}</span>
    </span>
  );
}

function sortTree(nodes: TreeNode[]): TreeNode[] {
  return nodes
    .sort(
      (left, right) =>
        left.entryKind.localeCompare(right.entryKind) || left.path.localeCompare(right.path),
    )
    .map((node) => ({
      ...node,
      children: node.children ? sortTree(node.children as TreeNode[]) : undefined,
    }));
}

function fileKey(path: string) {
  return `file:${path}`;
}

function directoryKey(path: string) {
  return `directory:${path}`;
}

function pathFromKey(value: string) {
  return value.replace(/^(?:file|directory):/, "");
}
