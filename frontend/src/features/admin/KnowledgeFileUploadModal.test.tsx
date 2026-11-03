import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const uploadObject = vi.hoisted(() => vi.fn());

vi.mock("@/shared/uploads", () => ({ uploadObject }));

import { KnowledgeFileUploadModal } from "@/features/admin/KnowledgeFileUploadModal";
import { server } from "@/test/server";

const ok = (data: unknown) =>
  HttpResponse.json({ code: "OK", message: "success", data, request_id: "req_test" });

const replacementDocument = {
  id: "document_test",
  tenant_id: "tenant_test",
  space_id: "space_test",
  title: "Current title",
  source_uri: null,
  status: "active",
  current_version: 1,
  chunk_count: 2,
  changed_by_display_name: "Operator",
  changed_by_user: { id: "user_operator", display_name: "Operator", avatar_present: false },
  created_at: "2026-07-14T10:00:00Z",
  updated_at: "2026-07-14T10:00:00Z",
};

function renderModal(onQueued = vi.fn(), replacement = false, onSourceIssued = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  render(
    <AntdApp>
      <QueryClientProvider client={client}>
        <KnowledgeFileUploadModal
          tenantId="tenant_test"
          spaceId="space_test"
          document={replacement ? replacementDocument : undefined}
          open
          onClose={onClose}
          onQueued={onQueued}
          onSourceIssued={onSourceIssued}
        />
      </QueryClientProvider>
    </AntdApp>,
  );
  return { onClose, onQueued, onSourceIssued };
}

function uploadInput() {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("Knowledge upload input is missing");
  return input;
}

beforeEach(() => {
  uploadObject.mockReset();
  uploadObject.mockImplementation(
    async ({
      contentType,
      file,
      onProgress,
      requestGrant,
    }: {
      contentType: string;
      file: File;
      onProgress?: (percent: number) => void;
      requestGrant: (metadata: unknown) => Promise<unknown>;
    }) => {
      onProgress?.(48);
      return requestGrant({ content_type: contentType, size_bytes: file.size });
    },
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("KnowledgeFileUploadModal", () => {
  it("uploads a selected file through a tenant-scoped grant and confirms ingestion", async () => {
    const user = userEvent.setup();
    let grantPayload: unknown;
    let confirmPayload: unknown;
    server.use(
      http.post(
        "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_test/document-upload-grants",
        async ({ request }) => {
          grantPayload = await request.json();
          return ok({
            source_id: "source_test",
            object_key: "staging/knowledge/tenant_test/space_test/source_test/upload.pdf",
            upload_key: "parrot/staging/knowledge/tenant_test/space_test/source_test/upload.pdf",
            upload_token: "upload_token",
            expires_at: "2026-07-14T10:00:00Z",
          });
        },
      ),
      http.post(
        "/api/v1/admin/tenants/tenant_test/knowledge/sources/source_test/confirm",
        async ({ request }) => {
          confirmPayload = await request.json();
          return ok({
            id: "ingestion_test",
            title: "Release policy",
            source_id: "source_test",
            document_id: "document_test",
            document_version_id: "version_test",
            status: "queued",
            attempts: 0,
            error_code: null,
            created_at: "2026-07-14T10:00:00Z",
            updated_at: "2026-07-14T10:00:00Z",
          });
        },
      ),
    );
    const { onClose, onQueued, onSourceIssued } = renderModal();
    const dialog = await screen.findByRole("dialog", { name: "批量上传知识文件" });

    expect(within(dialog).getByRole("button", { name: "选择多个文件" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "上传 0 个文件" })).toBeDisabled();
    expect(within(dialog).getByText(/一次最多选择 20 个/)).toBeInTheDocument();

    await user.upload(
      uploadInput(),
      new File(["pdf-content"], "policy.pdf", { type: "text/plain" }),
    );
    expect(within(dialog).getByRole("textbox", { name: "文档标题：policy.pdf" })).toHaveValue(
      "policy",
    );
    expect(within(dialog).getByRole("button", { name: "继续添加文件" })).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "上传 1 个文件" }));

    await waitFor(() =>
      expect(grantPayload).toEqual({
        title: "policy",
        filename: "policy.pdf",
        content_type: "application/pdf",
        size_bytes: 11,
      }),
    );
    expect(confirmPayload).toEqual({
      staging_key: "staging/knowledge/tenant_test/space_test/source_test/upload.pdf",
    });
    expect(uploadObject).toHaveBeenCalledWith(
      expect.objectContaining({ contentType: "application/pdf" }),
    );
    expect(onQueued).toHaveBeenCalledWith(
      expect.objectContaining({ id: "ingestion_test" }),
      "policy",
    );
    expect(onSourceIssued).toHaveBeenCalledWith("source_test");
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("rejects unsupported image files before a grant is requested", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderModal();

    await user.upload(uploadInput(), new File(["image"], "scan.png", { type: "image/png" }));

    expect(await screen.findByText(/当前仅支持 PDF、DOCX、MD 和 TXT 文件/)).toBeInTheDocument();
    expect(uploadObject).not.toHaveBeenCalled();
  });

  it("uploads a replacement without removing the current published version", async () => {
    const user = userEvent.setup();
    let grantPayload: unknown;
    server.use(
      http.post(
        "/api/v1/admin/tenants/tenant_test/knowledge/documents/document_test/version-upload-grants",
        async ({ request }) => {
          grantPayload = await request.json();
          return ok({
            source_id: "source_replacement",
            object_key: "staging/knowledge/replacement.pdf",
            upload_key: "parrot/staging/knowledge/replacement.pdf",
            upload_token: "upload_token",
            expires_at: "2026-07-14T10:00:00Z",
          });
        },
      ),
      http.post(
        "/api/v1/admin/tenants/tenant_test/knowledge/sources/source_replacement/confirm",
        () =>
          ok({
            id: "ingestion_replacement",
            title: "Release policy",
            source_id: "source_replacement",
            document_id: "document_test",
            document_version_id: "version_2",
            status: "queued",
            attempts: 0,
            error_code: null,
            created_at: "2026-07-14T10:00:00Z",
            updated_at: "2026-07-14T10:00:00Z",
          }),
      ),
    );
    renderModal(vi.fn(), true);
    const dialog = await screen.findByRole("dialog", { name: "上传新版本" });

    expect(within(dialog).getByText(/当前版本会继续参与检索/)).toBeInTheDocument();
    expect(within(dialog).getByRole("tab", { name: "上传文件" })).toBeInTheDocument();
    expect(within(dialog).getByRole("tab", { name: "录入文本" })).toBeInTheDocument();
    await user.upload(
      uploadInput(),
      new File(["pdf-content"], "replacement.pdf", { type: "application/pdf" }),
    );
    expect(within(dialog).getByText(/为“Current title”创建新版本/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "开始上传" }));

    await waitFor(() =>
      expect(grantPayload).toEqual({
        filename: "replacement.pdf",
        content_type: "application/pdf",
        size_bytes: 11,
      }),
    );
  });

  it("publishes a text replacement as a new version of the current document", async () => {
    const user = userEvent.setup();
    let payload: unknown;
    server.use(
      http.post(
        "/api/v1/admin/tenants/tenant_test/knowledge/documents/document_test/text-versions",
        async ({ request }) => {
          payload = await request.json();
          return ok({ ...replacementDocument, current_version: 2 });
        },
      ),
    );
    renderModal(vi.fn(), true);
    const dialog = await screen.findByRole("dialog", { name: "上传新版本" });

    await user.click(within(dialog).getByRole("tab", { name: "录入文本" }));
    await user.type(
      within(dialog).getByRole("textbox", { name: "新版本内容" }),
      "Deploy only after approval.",
    );
    await user.click(within(dialog).getByRole("button", { name: "发布新版本" }));

    await waitFor(() => expect(payload).toEqual({ content: "Deploy only after approval." }));
    expect(uploadObject).not.toHaveBeenCalled();
  });
});
