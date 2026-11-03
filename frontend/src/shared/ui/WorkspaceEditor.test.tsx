import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/shared/ui/monaco", () => ({}));
vi.mock("@monaco-editor/react", () => ({
  default: ({ options }: { options?: { fontSize?: number } }) => (
    <div data-font-size={options?.fontSize} data-testid="monaco-editor" />
  ),
}));

import { WorkspaceEditor } from "@/shared/ui/WorkspaceEditor";

describe("WorkspaceEditor", () => {
  it("uses a compact font size for source editing", () => {
    const { unmount } = render(
      <WorkspaceEditor
        activePath="main.py"
        files={[{ path: "main.py", content: "print('hello')", editable: true }]}
        onChange={vi.fn()}
        onOpen={vi.fn()}
      />,
    );

    expect(screen.getByTestId("monaco-editor")).toHaveAttribute("data-font-size", "13");
    unmount();
  });

  it("keeps a custom editor in its own scrollable content pane", () => {
    const { unmount } = render(
      <WorkspaceEditor
        activePath="manifest.json"
        files={[{ path: "manifest.json", content: "{}", editable: true }]}
        onChange={vi.fn()}
        onOpen={vi.fn()}
        renderEditor={() => <div>结构化表单</div>}
      />,
    );

    expect(document.querySelector(".workspace-editor__content")).toHaveClass(
      "workspace-editor__content--custom",
    );
    unmount();
  });

  it("creates and deletes draft entries from the resizable tree", async () => {
    const user = userEvent.setup();
    const onCreateFile = vi.fn().mockResolvedValue(undefined);
    const onCreateDirectory = vi.fn().mockResolvedValue(undefined);
    const onDelete = vi.fn().mockResolvedValue(undefined);
    const onPreview = vi.fn();
    render(
      <WorkspaceEditor
        activePath={null}
        files={[
          { path: "SKILL.md", editable: true },
          { path: "scripts/run.py", editable: true },
        ]}
        onChange={vi.fn()}
        onCreateDirectory={onCreateDirectory}
        onCreateFile={onCreateFile}
        onDelete={onDelete}
        onOpen={vi.fn()}
        onPreview={onPreview}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByRole("separator")).toBeInTheDocument();
    expect(document.querySelector(".ant-splitter-panel")).toHaveStyle({ flexBasis: "280px" });
    expect(document.querySelector('[data-icon="Folder"]')).toBeInTheDocument();
    expect(document.querySelector('[data-icon="FileText"]')).toBeInTheDocument();
    expect(document.querySelector('[data-icon="FileAddition"]')).toBeInTheDocument();
    expect(document.querySelector('[data-icon="FolderPlus"]')).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新文件" })).toHaveTextContent("");
    expect(screen.getByRole("button", { name: "新建文件" })).toHaveTextContent("");
    expect(screen.getByRole("button", { name: "新建目录" })).toHaveTextContent("");
    expect(screen.getByRole("button", { name: "删除所选文件或目录" })).toHaveTextContent("");
    expect(
      screen.getByTitle("SKILL.md").closest(".workspace-editor__tree-node--root-file"),
    ).toBeInTheDocument();
    expect(
      screen.getByTitle("run.py").closest(".workspace-editor__tree-node--root-file"),
    ).toBeNull();
    await user.click(screen.getByRole("button", { name: "大屏预览" }));
    expect(onPreview).toHaveBeenCalledOnce();

    await user.click(screen.getByRole("button", { name: "新建文件" }));
    const createDialog = await screen.findByRole("dialog", { name: "新建文件" });
    await user.type(
      within(createDialog).getByRole("textbox", { name: "相对路径" }),
      "scripts/run.py",
    );
    await user.click(within(createDialog).getByRole("button", { name: "OK" }));
    expect(onCreateFile).toHaveBeenCalledWith("scripts/run.py");

    await user.click(screen.getByTitle("SKILL.md"));
    const deleteButton = screen.getByRole("button", { name: "删除所选文件或目录" });
    await waitFor(() => expect(deleteButton).toBeEnabled());
    await user.click(deleteButton);
    await screen.findByText(/确定删除/);
    const confirmDeleteButton = screen
      .getAllByRole("button", { name: /删\s*除/ })
      .find((button) => button.getAttribute("aria-label") !== "删除所选文件或目录");
    if (!confirmDeleteButton) throw new Error("Expected the delete confirmation button");
    await user.click(confirmDeleteButton);
    expect(onDelete).toHaveBeenCalledWith("SKILL.md");
  });

  it("shows a loading state in the file tree while refreshing", () => {
    const { container } = render(
      <WorkspaceEditor
        activePath={null}
        files={[{ path: "SKILL.md", editable: true }]}
        refreshingFiles
        onChange={vi.fn()}
        onOpen={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    expect(container.querySelector(".workspace-editor__tree .ant-spin-text")).toHaveTextContent(
      "正在刷新文件",
    );
    expect(within(container).getByRole("button", { name: "刷新文件" })).toBeDisabled();
    expect(container.querySelector(".workspace-editor__tree-content")).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });
});
