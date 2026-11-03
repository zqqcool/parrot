import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SkillManifestForm } from "@/features/admin/SkillManifestForm";

afterEach(cleanup);

describe("SkillManifestForm", () => {
  it("hides sandbox settings when an executable Skill becomes instruction-only", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <SkillManifestForm
        content='{"execute":true,"runtime":"python","entrypoint":"scripts/main.py"}'
        onChange={onChange}
      />,
    );

    expect(screen.queryByText("输入 Schema")).not.toBeInTheDocument();
    expect(screen.queryByText("输出 Schema")).not.toBeInTheDocument();
    expect(screen.queryByText("副作用级别")).not.toBeInTheDocument();

    await user.click(screen.getByRole("switch", { checked: true }));

    await waitFor(() => {
      expect(onChange).toHaveBeenLastCalledWith('{\n  "execute": false\n}\n');
    });
    expect(screen.queryByText("执行环境")).not.toBeInTheDocument();
    expect(screen.queryByText("入口文件")).not.toBeInTheDocument();
    expect(screen.queryByText("网络与环境变量")).not.toBeInTheDocument();
    expect(screen.getByText("不会启动沙盒")).toBeInTheDocument();
  });

  it("reveals sandbox settings only after enabling execution", async () => {
    const user = userEvent.setup();

    render(<SkillManifestForm content='{"execute":false}' onChange={vi.fn()} />);

    expect(screen.queryByText("执行环境")).not.toBeInTheDocument();
    expect(screen.getByText("不会启动沙盒")).toBeInTheDocument();

    await user.click(screen.getByRole("switch", { checked: false }));

    expect(screen.getByText("执行环境")).toBeInTheDocument();
    expect(screen.getByText("入口文件")).toBeInTheDocument();
    expect(screen.getByText("网络与环境变量")).toBeInTheDocument();
  });

  it("supports direct JSON edits without silently resetting invalid content", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(<ManifestHarness initialContent='{"execute":false}' onChange={onChange} />);

    await user.click(screen.getByText("JSON"));
    const editor = screen.getByRole("textbox", { name: "manifest JSON" });
    await user.clear(editor);
    await user.paste('{"execute": true');

    expect(editor).toHaveValue('{"execute": true');
    expect(onChange).toHaveBeenLastCalledWith('{"execute": true');
    expect(
      screen.getByText("manifest.json 不是有效的 JSON，请在 JSON 模式中修复后再保存。"),
    ).toBeInTheDocument();

    await user.click(screen.getByText("表单配置"));

    expect(screen.getByText("前往 JSON 编辑")).toBeInTheDocument();
    expect(screen.queryByText("Skill 类型")).not.toBeInTheDocument();
  });
});

function ManifestHarness({
  initialContent,
  onChange,
}: {
  initialContent: string;
  onChange: (value: string) => void;
}) {
  const [content, setContent] = useState(initialContent);
  return (
    <SkillManifestForm
      content={content}
      onChange={(value) => {
        onChange(value);
        setContent(value);
      }}
    />
  );
}
