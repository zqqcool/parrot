import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { HttpClient, HttpClientError, toUserErrorMessage } from "@/shared/http";
import { server } from "@/test/server";

describe("HttpClient", () => {
  it("sends cookie credentials, request IDs, CSRF, and idempotency keys", async () => {
    server.use(
      http.post("/api/test", async ({ request }) => {
        expect(request.credentials).toBe("include");
        expect(request.headers.get("authorization")).toBeNull();
        expect(request.headers.get("x-request-id")).toMatch(/^req_web_/);
        expect(request.headers.get("x-csrf-token")).toBe("csrf_test");
        expect(request.headers.get("idempotency-key")).toMatch(/^idem_web_/);
        expect(await request.json()).toEqual({ value: 1 });
        return HttpResponse.json({
          code: "OK",
          message: "success",
          data: { saved: true },
          request_id: "req_test",
        });
      }),
    );
    const client = new HttpClient();
    client.setCsrfToken("csrf_test");
    await expect(
      client.post<{ saved: boolean }>("/api/test", { value: 1 }, { idempotencyKey: true }),
    ).resolves.toEqual({ saved: true });
  });

  it("sends requests when crypto.randomUUID is unavailable", async () => {
    server.use(
      http.post("/api/login-without-random-uuid", ({ request }) => {
        expect(request.headers.get("x-request-id")).toMatch(/^req_web_[0-9a-f]{32}$/);
        return HttpResponse.json({
          code: "OK",
          message: "success",
          data: { accepted: true },
          request_id: "req_test",
        });
      }),
    );
    const originalDescriptor = Object.getOwnPropertyDescriptor(crypto, "randomUUID");
    Object.defineProperty(crypto, "randomUUID", { configurable: true, value: undefined });
    const fetchSpy = vi.spyOn(window, "fetch");

    try {
      await expect(
        new HttpClient().post<{ accepted: boolean }>("/api/login-without-random-uuid", {}),
      ).resolves.toEqual({ accepted: true });
      expect(fetchSpy).toHaveBeenCalledOnce();
    } finally {
      fetchSpy.mockRestore();
      if (originalDescriptor) {
        Object.defineProperty(crypto, "randomUUID", originalDescriptor);
      } else {
        Reflect.deleteProperty(crypto, "randomUUID");
      }
    }
  });

  it("normalizes backend errors and notifies on 401", async () => {
    server.use(
      http.get("/api/protected", () =>
        HttpResponse.json(
          {
            code: "UNAUTHORIZED",
            message: "Authentication required",
            details: [],
            request_id: "req_401",
          },
          { status: 401 },
        ),
      ),
    );
    const client = new HttpClient();
    let notified = false;
    client.onUnauthorized(() => {
      notified = true;
    });
    await expect(client.get("/api/protected")).rejects.toMatchObject({
      status: 401,
      code: "UNAUTHORIZED",
      requestId: "req_401",
    });
    expect(notified).toBe(true);
  });

  it("sends multipart data without a JSON content type", async () => {
    let contentType = "";
    server.use(
      http.post("/api/avatar", ({ request }) => {
        contentType = request.headers.get("content-type") ?? "";
        return HttpResponse.json({
          code: "OK",
          message: "success",
          data: { uploaded: true },
          request_id: "req_avatar",
        });
      }),
    );
    const client = new HttpClient();
    const form = new FormData();
    form.append("file", new File(["avatar"], "avatar.png", { type: "image/png" }));

    await expect(client.postForm<{ uploaded: boolean }>("/api/avatar", form)).resolves.toEqual({
      uploaded: true,
    });
    expect(contentType).toContain("multipart/form-data");
  });

  it("downloads authorized files and decodes the server filename", async () => {
    server.use(
      http.get(
        "/api/source",
        () =>
          new HttpResponse("knowledge", {
            headers: {
              "Content-Disposition": "attachment; filename*=UTF-8''release%20guide.txt",
              "Content-Type": "text/plain",
            },
          }),
      ),
    );
    const client = new HttpClient();

    const downloaded = await client.getFile("/api/source");

    expect(downloaded.filename).toBe("release guide.txt");
    await expect(downloaded.blob.text()).resolves.toBe("knowledge");
  });

  it("does not send Content-Type on GET or file downloads", async () => {
    let getContentType: string | null = "unset";
    let fileContentType: string | null = "unset";
    server.use(
      http.get("/api/items", ({ request }) => {
        getContentType = request.headers.get("content-type");
        return HttpResponse.json({
          code: "OK",
          message: "success",
          data: { ok: true },
          request_id: "req_get",
        });
      }),
      http.get("/api/file", ({ request }) => {
        fileContentType = request.headers.get("content-type");
        return new HttpResponse("bin", {
          headers: { "Content-Type": "application/octet-stream" },
        });
      }),
    );
    const client = new HttpClient();

    await expect(client.get<{ ok: boolean }>("/api/items")).resolves.toEqual({ ok: true });
    await expect(client.getFile("/api/file")).resolves.toMatchObject({
      filename: "knowledge-source",
    });
    expect(getContentType).toBeNull();
    expect(fileContentType).toBeNull();
  });

  it("maps backend error codes to user-facing Chinese messages", async () => {
    server.use(
      http.post("/api/login", () =>
        HttpResponse.json(
          {
            code: "AUTH_INVALID_CREDENTIALS",
            message: "用户名或密码错误。",
            details: [],
            request_id: "req_login",
          },
          { status: 401 },
        ),
      ),
    );
    const client = new HttpClient();
    const error = await client.post("/api/login", {}).catch((reason: unknown) => reason);

    expect(toUserErrorMessage(error, "登录失败")).toBe("用户名或密码错误。");
    expect(toUserErrorMessage(new Error("Internal details"), "操作失败")).toBe("操作失败");
  });

  it("uses the backend response message for known API errors", () => {
    const error = new HttpClientError({
      status: 409,
      statusText: "Conflict",
      url: "/api/v1/admin/tenants/tenant_test/skills/skill_test",
      payload: {
        code: "SKILL_IN_USE",
        message: "该 Skill 仍被智能体绑定，请先解除关联后再删除。",
        details: [],
        request_id: "req_skill_in_use",
      },
    });

    expect(toUserErrorMessage(error, "操作失败")).toBe(
      "该 Skill 仍被智能体绑定，请先解除关联后再删除。",
    );
  });

  it("does not replace a backend message with a frontend error-code map", () => {
    const error = new HttpClientError({
      status: 409,
      statusText: "Conflict",
      url: "/api/v1/admin/tenants/tenant_test/knowledge/spaces/space_test",
      payload: {
        code: "KNOWLEDGE_SPACE_NOT_EMPTY",
        message: "知识库仍包含文档、上传源或智能体关联，无法删除。",
        details: [
          { field: "documents", reason: "20" },
          { field: "sources", reason: "19" },
        ],
        request_id: "req_knowledge_conflict",
      },
    });

    expect(toUserErrorMessage(error, "删除知识库失败")).toBe(
      "知识库仍包含文档、上传源或智能体关联，无法删除。",
    );
  });
});
