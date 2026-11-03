import { HttpClientError, HttpNetworkError } from "@/shared/http/errors";
import type {
  ApiErrorResponse,
  ApiResponse,
  DownloadedFile,
  HttpRequestOptions,
} from "@/shared/http/types";
import { newRandomId } from "@/shared/randomId";

type HttpMethod = "DELETE" | "GET" | "PATCH" | "POST" | "PUT";
type HttpClientConfig = { baseUrl?: string; timeoutMs?: number };

export class HttpClient {
  private readonly baseUrl: string;
  private readonly defaultTimeoutMs: number;
  private csrfToken: string | null = null;
  private unauthorizedHandler: (() => void) | null = null;

  constructor(config: HttpClientConfig = {}) {
    this.baseUrl = trimTrailingSlash(config.baseUrl ?? "");
    this.defaultTimeoutMs = config.timeoutMs ?? 12_000;
  }

  setCsrfToken(value: string | null): void {
    this.csrfToken = value;
  }

  onUnauthorized(handler: (() => void) | null): void {
    this.unauthorizedHandler = handler;
  }

  get<T>(path: string, options: HttpRequestOptions = {}): Promise<T> {
    return this.request<T>("GET", path, undefined, options);
  }

  async getFile(path: string, options: HttpRequestOptions = {}): Promise<DownloadedFile> {
    let lastError: unknown;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        return await this.executeFile(path, options);
      } catch (error) {
        lastError = error;
        if (!shouldRetry(error) || attempt === 1) throw error;
      }
    }
    throw lastError;
  }

  post<T>(path: string, body: unknown, options: HttpRequestOptions = {}): Promise<T> {
    return this.request<T>("POST", path, body, options);
  }

  postForm<T>(path: string, body: FormData, options: HttpRequestOptions = {}): Promise<T> {
    return this.request<T>("POST", path, body, options);
  }

  put<T>(path: string, body: unknown, options: HttpRequestOptions = {}): Promise<T> {
    return this.request<T>("PUT", path, body, options);
  }

  patch<T>(path: string, body: unknown, options: HttpRequestOptions = {}): Promise<T> {
    return this.request<T>("PATCH", path, body, options);
  }

  delete<T>(path: string, body: unknown, options: HttpRequestOptions = {}): Promise<T> {
    return this.request<T>("DELETE", path, body, options);
  }

  private async request<T>(
    method: HttpMethod,
    path: string,
    body: unknown,
    options: HttpRequestOptions,
  ): Promise<T> {
    const attempts = method === "GET" || options.idempotencyKey ? 2 : 1;
    let lastError: unknown;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        return await this.execute<T>(method, path, body, options);
      } catch (error) {
        lastError = error;
        if (!shouldRetry(error) || attempt + 1 >= attempts) throw error;
      }
    }
    throw lastError;
  }

  private async execute<T>(
    method: HttpMethod,
    path: string,
    body: unknown,
    options: HttpRequestOptions,
  ): Promise<T> {
    const { response, url } = await this.fetchResponse(method, path, body, options);
    return this.unwrap<T>(response, url);
  }

  private async executeFile(path: string, options: HttpRequestOptions): Promise<DownloadedFile> {
    const { response, url } = await this.fetchResponse("GET", path, undefined, options);
    if (!response.ok) {
      const payload = await readPayload<never>(response);
      if (response.status === 401) this.unauthorizedHandler?.();
      throw new HttpClientError({
        status: response.status,
        statusText: response.statusText,
        url,
        payload: payload ? normalizeError(payload, response) : undefined,
      });
    }
    return {
      blob: await response.blob(),
      filename: responseFilename(response.headers.get("content-disposition")),
    };
  }

  private async fetchResponse(
    method: HttpMethod,
    path: string,
    body: unknown,
    options: HttpRequestOptions,
  ): Promise<{ response: Response; url: string }> {
    const url = this.toUrl(path);
    const controller = new AbortController();
    const timeout = window.setTimeout(
      () => controller.abort("timeout"),
      options.timeoutMs ?? this.defaultTimeoutMs,
    );
    const abort = () => controller.abort(options.signal?.reason);
    options.signal?.addEventListener("abort", abort, { once: true });
    const requestBody = serializeRequestBody(body);
    const headers = this.buildHeaders(method, options, requestBody.hasJsonBody);

    try {
      const response = await fetch(url, {
        method,
        credentials: "include",
        headers,
        body: requestBody.value,
        signal: controller.signal,
      });
      return { response, url };
    } catch (error) {
      if (error instanceof HttpClientError) throw error;
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new HttpNetworkError(url);
    } finally {
      window.clearTimeout(timeout);
      options.signal?.removeEventListener("abort", abort);
    }
  }

  private buildHeaders(
    method: HttpMethod,
    options: HttpRequestOptions,
    hasJsonBody: boolean,
  ): Record<string, string> {
    const headers: Record<string, string> = { "X-Request-Id": options.requestId ?? newRequestId() };
    // Only JSON bodies need Content-Type. GET/file downloads must not advertise a body type —
    // some Vite/http-proxy paths mishandle GET + application/json as a broken proxied response.
    if (hasJsonBody) headers["Content-Type"] = "application/json";
    if (method !== "GET" && this.csrfToken) headers["X-CSRF-Token"] = this.csrfToken;
    if (options.idempotencyKey) {
      headers["Idempotency-Key"] =
        options.idempotencyKey === true ? newIdempotencyKey() : options.idempotencyKey;
    }
    return headers;
  }

  private async unwrap<T>(response: Response, url: string): Promise<T> {
    const payload = await readPayload<T>(response);
    if (!response.ok || !payload || payload.code !== "OK") {
      if (response.status === 401) this.unauthorizedHandler?.();
      throw new HttpClientError({
        status: response.status,
        statusText: response.statusText,
        url,
        payload: payload ? normalizeError(payload, response) : undefined,
      });
    }
    return (payload as ApiResponse<T>).data;
  }

  private toUrl(path: string): string {
    if (!path.startsWith("/")) throw new Error(`HTTP path must be absolute: ${path}`);
    return `${this.baseUrl}${path}`;
  }
}

function serializeRequestBody(body: unknown): {
  value: BodyInit | undefined;
  hasJsonBody: boolean;
} {
  if (body === undefined) return { value: undefined, hasJsonBody: false };
  if (body instanceof FormData) return { value: body, hasJsonBody: false };
  return { value: JSON.stringify(body), hasJsonBody: true };
}

function responseFilename(header: string | null): string {
  const encoded = header?.match(/filename\*\s*=\s*UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try {
      return safeFilename(decodeURIComponent(encoded.trim()));
    } catch {
      // Fall back to the plain filename or a safe default.
    }
  }
  const plain = header?.match(/filename\s*=\s*"?([^";]+)"?/i)?.[1];
  return safeFilename(plain?.trim() ?? "knowledge-source");
}

function safeFilename(value: string): string {
  const parts = value.replace(/\\/g, "/").split("/");
  const basename = parts[parts.length - 1] ?? "";
  const printable = [...basename]
    .filter((character) => {
      const code = character.charCodeAt(0);
      return code >= 32 && code !== 127;
    })
    .join("");
  return printable.slice(0, 300) || "knowledge-source";
}

async function readPayload<T>(
  response: Response,
): Promise<ApiResponse<T> | ApiErrorResponse | null> {
  if (!(response.headers.get("content-type") ?? "").includes("application/json")) return null;
  try {
    return (await response.json()) as ApiResponse<T> | ApiErrorResponse;
  } catch {
    return null;
  }
}

function normalizeError<T>(
  payload: ApiResponse<T> | ApiErrorResponse,
  response: Response,
): ApiErrorResponse {
  return {
    code: payload.code || `HTTP_${response.status}`,
    message: payload.message || response.statusText || "Request failed",
    details: "details" in payload ? payload.details : [],
    request_id: payload.request_id,
  };
}

function shouldRetry(error: unknown): boolean {
  return (
    error instanceof HttpNetworkError ||
    (error instanceof HttpClientError && [502, 503, 504].includes(error.status))
  );
}

function newRequestId(): string {
  return `req_web_${newRandomId()}`;
}

function newIdempotencyKey(): string {
  return `idem_web_${newRandomId()}`;
}

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}
