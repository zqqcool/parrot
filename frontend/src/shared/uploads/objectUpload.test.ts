import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ subscribe: vi.fn(), unsubscribe: vi.fn() }));

vi.mock("qiniu-js", () => ({
  upload: vi.fn(() => ({ subscribe: mocks.subscribe })),
}));

import * as qiniu from "qiniu-js";

import { uploadObject } from "@/shared/uploads";

describe("uploadObject", () => {
  beforeEach(() => {
    mocks.subscribe.mockReset();
    mocks.unsubscribe.mockReset();
    mocks.subscribe.mockImplementation(({ complete }: { complete: () => void }) => {
      complete();
      return { unsubscribe: mocks.unsubscribe };
    });
  });

  it("keeps a Qiniu upload token in memory and uploads only to its issued key", async () => {
    const requestGrant = vi.fn().mockResolvedValue({
      object_key: "staging/tenant_test/upload_test",
      upload_key: "parrot/staging/tenant_test/upload_test",
      upload_token: "qiniu-upload-token",
      expires_at: "2026-07-13T12:00:00Z",
    });
    const file = new File(["content"], "avatar.png", { type: "image/png" });

    const result = await uploadObject({ file, requestGrant });

    expect(requestGrant).toHaveBeenCalledWith({ content_type: "image/png", size_bytes: 7 });
    expect(qiniu.upload).toHaveBeenCalledWith(
      file,
      "parrot/staging/tenant_test/upload_test",
      "qiniu-upload-token",
      { fname: "avatar.png", mimeType: "image/png" },
      { useCdnDomain: false, disableStatisticsReport: true },
    );
    expect(result.object_key).toBe("staging/tenant_test/upload_test");
  });

  it("cancels the Qiniu subscription when the caller aborts", async () => {
    mocks.subscribe.mockImplementation(() => ({ unsubscribe: mocks.unsubscribe }));
    const requestGrant = vi.fn().mockResolvedValue({
      object_key: "staging/tenant_test/upload_test",
      upload_key: "parrot/staging/tenant_test/upload_test",
      upload_token: "qiniu-upload-token",
      expires_at: "2026-07-13T12:00:00Z",
    });
    const controller = new AbortController();
    const upload = uploadObject({
      file: new File(["content"], "avatar.png", { type: "image/png" }),
      requestGrant,
      signal: controller.signal,
    });

    controller.abort();

    await expect(upload).rejects.toThrow("Upload cancelled");
    expect(mocks.unsubscribe).toHaveBeenCalledOnce();
  });

  it("uses an explicit content type when a feature normalizes an upload", async () => {
    const requestGrant = vi.fn().mockResolvedValue({
      object_key: "staging/tenant_test/upload_test",
      upload_key: "parrot/staging/tenant_test/upload_test",
      upload_token: "qiniu-upload-token",
      expires_at: "2026-07-13T12:00:00Z",
    });

    await uploadObject({
      file: new File(["# Release"], "release.md", { type: "text/plain" }),
      contentType: "text/markdown",
      requestGrant,
    });

    expect(requestGrant).toHaveBeenCalledWith({ content_type: "text/markdown", size_bytes: 9 });
    expect(qiniu.upload).toHaveBeenCalledWith(
      expect.any(File),
      "parrot/staging/tenant_test/upload_test",
      "qiniu-upload-token",
      { fname: "release.md", mimeType: "text/markdown" },
      { useCdnDomain: false, disableStatisticsReport: true },
    );
  });

  it("reports Qiniu upload progress and completion", async () => {
    mocks.subscribe.mockImplementation(
      ({
        complete,
        next,
      }: {
        complete: () => void;
        next: (progress: { total: { percent: number } }) => void;
      }) => {
        next({ total: { percent: 42.5 } });
        complete();
        return { unsubscribe: mocks.unsubscribe };
      },
    );
    const onProgress = vi.fn();

    await uploadObject({
      file: new File(["content"], "policy.pdf", { type: "application/pdf" }),
      onProgress,
      requestGrant: vi.fn().mockResolvedValue({
        object_key: "staging/tenant_test/upload_test",
        upload_key: "parrot/staging/tenant_test/upload_test",
        upload_token: "qiniu-upload-token",
        expires_at: "2026-07-13T12:00:00Z",
      }),
    });

    expect(onProgress).toHaveBeenNthCalledWith(1, 42.5);
    expect(onProgress).toHaveBeenLastCalledWith(100);
  });
});
