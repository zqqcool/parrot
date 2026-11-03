import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KnowledgeIngestionNotice } from "@/features/admin/KnowledgeIngestionNotice";
import type { IngestionQueueItem } from "@/features/admin/useKnowledgeDocuments";

function item(
  id: string,
  title: string,
  status: string,
  errorCode: string | null = null,
): IngestionQueueItem {
  return {
    id,
    title,
    spaceId: "space_test",
    status,
    errorCode,
    error: null,
    initial: {
      id,
      title,
      source_id: `source_${id}`,
      document_id: `document_${id}`,
      document_version_id: `version_${id}`,
      status,
      attempts: 0,
      error_code: errorCode,
      created_at: "2026-07-15T10:00:00Z",
      updated_at: "2026-07-15T10:00:00Z",
    },
  };
}

afterEach(cleanup);

describe("KnowledgeIngestionNotice", () => {
  it("summarizes multiple active jobs in one expandable progress panel", () => {
    render(
      <KnowledgeIngestionNotice
        items={[item("job_a", "Policy", "running"), item("job_b", "Guide", "queued")]}
        onDismiss={vi.fn()}
      />,
    );

    expect(screen.getByText("正在处理 2 个知识文件")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "知识文件处理阶段进度" })).toBeInTheDocument();
    expect(screen.getByText("Policy")).toBeInTheDocument();
    expect(screen.getByText("提取与切分中")).toBeInTheDocument();
    expect(screen.getByText("Guide")).toBeInTheDocument();
    expect(screen.getByText("等待处理")).toBeInTheDocument();
  });

  it("shows a compact final summary and allows clearing it", async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    render(
      <KnowledgeIngestionNotice
        items={[
          item("job_a", "Policy", "succeeded"),
          item("job_b", "Guide", "failed", "extract_failed"),
        ]}
        onDismiss={onDismiss}
      />,
    );

    expect(screen.getByText("知识文件处理完成：1 个成功，1 个失败")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "清除记录" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});
