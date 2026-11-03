import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { App as AntdApp } from "antd";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UserAvatarUpload } from "@/features/admin/UserAvatarUpload";

afterEach(cleanup);

describe("UserAvatarUpload", () => {
  it("accepts a supported avatar file", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { container } = render(
      <AntdApp>
        <UserAvatarUpload file={null} onChange={onChange} />
      </AntdApp>,
    );
    const file = new File(["avatar"], "avatar.png", { type: "image/png" });
    const input = container.querySelector('input[type="file"]');

    expect(input).not.toBeNull();
    expect(screen.getByRole("button", { name: "选择头像" })).toHaveTextContent("点击上传头像");
    await user.upload(input as HTMLInputElement, file);

    expect(onChange).toHaveBeenCalledWith(file);
  });

  it("rejects an unsupported file type", async () => {
    const onChange = vi.fn();
    const { container } = render(
      <AntdApp>
        <UserAvatarUpload file={null} onChange={onChange} />
      </AntdApp>,
    );
    const input = container.querySelector('input[type="file"]');

    expect(input).not.toBeNull();
    fireEvent.change(input as HTMLInputElement, {
      target: { files: [new File(["avatar"], "avatar.svg", { type: "image/svg+xml" })] },
    });

    expect(onChange).not.toHaveBeenCalled();
    expect(await screen.findByText("仅支持 PNG、JPEG 或 WebP 图片")).toBeInTheDocument();
  });
});
