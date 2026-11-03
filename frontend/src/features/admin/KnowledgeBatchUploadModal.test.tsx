import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const uploadObject = vi.hoisted(() => vi.fn());

vi.mock("@/shared/uploads", () => ({ uploadObject }));

import { KnowledgeBatchUploadModal } from "@/features/admin/KnowledgeBatchUploadModal";
import { server } from "@/test/server";

const ok = (data: unknown) =>
  HttpResponse.json({ code: "OK", message: "success", data, request_id: "req_test" });

function renderModal(onQueued = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  render(
    <AntdApp>
      <QueryClientProvider client={client}>
        <KnowledgeBatchUploadModal
          tenantId="tenant_test"
          spaceId="space_test"
          open
          onClose={onClose}
          onQueued={onQueued}
        />
      </QueryClientProvider>
    </AntdApp>,
  );
  return { onClose };
}

function uploadInput() {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("Knowledge upload input is missing");
  return input;
}

function installSuccessHandlers(grantPayloads: Array<Record<string, unknown>> = []) {
  server.use(
    http.post(
      "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_test/document-upload-grants",
      async ({ request }) => {
        const payload = (await request.json()) as Record<string, unknown>;
        grantPayloads.push(payload);
        const source = String(payload.filename).replace(/\W/g, "_");
        return ok({
          source_id: `source_${source}`,
          object_key: `staging/${source}`,
          upload_key: `parrot/staging/${source}`,
          upload_token: "upload_token",
          expires_at: "2026-07-14T10:00:00Z",
        });
      },
    ),
    http.post(
      "/api/v1/admin/tenants/tenant_test/knowledge/sources/:sourceId/confirm",
      ({ params }) => {
        const sourceId = String(params.sourceId);
        return ok({
          id: `ingestion_${sourceId}`,
          title: sourceId,
          source_id: sourceId,
          document_id: `document_${sourceId}`,
          document_version_id: `version_${sourceId}`,
          status: "queued",
          attempts: 0,
          error_code: null,
          created_at: "2026-07-14T10:00:00Z",
          updated_at: "2026-07-14T10:00:00Z",
        });
      },
    ),
  );
}

beforeEach(() => {
  uploadObject.mockReset();
  uploadObject.mockImplementation(
    async ({
      contentType,
      file,
      requestGrant,
    }: {
      contentType: string;
      file: File;
      requestGrant: (metadata: unknown) => Promise<unknown>;
    }) => requestGrant({ content_type: contentType, size_bytes: file.size }),
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("KnowledgeBatchUploadModal", () => {
  it("selects and uploads multiple files as one batch", async () => {
    const user = userEvent.setup();
    const grantPayloads: Array<Record<string, unknown>> = [];
    installSuccessHandlers(grantPayloads);
    const onQueued = vi.fn();
    const { onClose } = renderModal(onQueued);
    const dialog = await screen.findByRole("dialog", { name: "批量上传知识文件" });

    await user.upload(uploadInput(), [
      new File(["pdf"], "policy.pdf", { type: "application/pdf" }),
      new File(["# guide"], "guide.md", { type: "text/markdown" }),
    ]);

    expect(within(dialog).getByRole("textbox", { name: "文档标题：policy.pdf" })).toHaveValue(
      "policy",
    );
    expect(within(dialog).getByRole("textbox", { name: "文档标题：guide.md" })).toHaveValue(
      "guide",
    );
    await user.click(within(dialog).getByRole("button", { name: "上传 2 个文件" }));

    await waitFor(() => expect(onQueued).toHaveBeenCalledTimes(2));
    expect(grantPayloads).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ filename: "policy.pdf", content_type: "application/pdf" }),
        expect.objectContaining({ filename: "guide.md", content_type: "text/markdown" }),
      ]),
    );
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("only shows overall progress after an upload starts", async () => {
    const user = userEvent.setup();
    let finishUpload: (() => void) | undefined;
    uploadObject.mockImplementation(
      ({ contentType, file, requestGrant }: UploadInvocation) =>
        new Promise((resolve) => {
          finishUpload = () =>
            resolve(requestGrant({ content_type: contentType, size_bytes: file.size }));
        }),
    );
    installSuccessHandlers();
    const onQueued = vi.fn();
    renderModal(onQueued);
    const dialog = await screen.findByRole("dialog", { name: "批量上传知识文件" });

    await user.upload(uploadInput(), new File(["# guide"], "guide.md", { type: "text/markdown" }));

    expect(within(dialog).queryByLabelText("批量上传总体进度")).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "上传 1 个文件" }));
    expect(await within(dialog).findByLabelText("批量上传总体进度")).toBeInTheDocument();

    finishUpload?.();
    await waitFor(() => expect(onQueued).toHaveBeenCalledOnce());
  });

  it("keeps a partial batch open and retries only failed files", async () => {
    const user = userEvent.setup();
    let guideAttempts = 0;
    uploadObject.mockImplementation(
      async ({ contentType, file, requestGrant }: UploadInvocation) => {
        if (file.name === "guide.md" && guideAttempts++ === 0) {
          throw new Error("network interrupted");
        }
        return requestGrant({ content_type: contentType, size_bytes: file.size });
      },
    );
    installSuccessHandlers();
    const onQueued = vi.fn();
    const { onClose } = renderModal(onQueued);
    const dialog = await screen.findByRole("dialog", { name: "批量上传知识文件" });
    await user.upload(uploadInput(), [
      new File(["pdf"], "policy.pdf", { type: "application/pdf" }),
      new File(["# guide"], "guide.md", { type: "text/markdown" }),
    ]);

    await user.click(within(dialog).getByRole("button", { name: "上传 2 个文件" }));

    expect(await within(dialog).findByText("上传失败，请稍后重试。")).toBeInTheDocument();
    expect(onQueued).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "重试 1 个失败文件" }));

    await waitFor(() => expect(onQueued).toHaveBeenCalledTimes(2));
    expect(uploadObject).toHaveBeenCalledTimes(3);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("automatically retries an idempotent confirmation after a retryable failure", async () => {
    const user = userEvent.setup();
    let confirmAttempts = 0;
    const idempotencyKeys: Array<string | null> = [];
    installSuccessHandlers();
    server.use(
      http.post(
        "/api/v1/admin/tenants/tenant_test/knowledge/sources/:sourceId/confirm",
        ({ params, request }) => {
          confirmAttempts += 1;
          idempotencyKeys.push(request.headers.get("idempotency-key"));
          if (confirmAttempts === 1) {
            return HttpResponse.json(
              {
                code: "DEPENDENCY_UNAVAILABLE",
                message: "服务依赖尚未就绪，请稍后重试。",
                details: [],
                request_id: "req_failed",
              },
              { status: 503 },
            );
          }
          const sourceId = String(params.sourceId);
          return ok({
            id: `ingestion_${sourceId}`,
            title: sourceId,
            source_id: sourceId,
            document_id: `document_${sourceId}`,
            document_version_id: `version_${sourceId}`,
            status: "queued",
            attempts: 0,
            error_code: null,
            created_at: "2026-07-14T10:00:00Z",
            updated_at: "2026-07-14T10:00:00Z",
          });
        },
      ),
    );
    const onQueued = vi.fn();
    const { onClose } = renderModal(onQueued);
    const dialog = await screen.findByRole("dialog", { name: "批量上传知识文件" });
    await user.upload(uploadInput(), new File(["# guide"], "guide.md", { type: "text/markdown" }));

    await user.click(within(dialog).getByRole("button", { name: "上传 1 个文件" }));

    await waitFor(() => expect(onQueued).toHaveBeenCalledOnce());
    expect(confirmAttempts).toBe(2);
    expect(idempotencyKeys).toEqual([
      "knowledge-confirm:source_guide_md",
      "knowledge-confirm:source_guide_md",
    ]);
    expect(onClose).toHaveBeenCalledOnce();
  });
});

type UploadInvocation = {
  contentType: string;
  file: File;
  requestGrant: (metadata: unknown) => Promise<unknown>;
};
