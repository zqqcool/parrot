import type { ApiErrorResponse } from "@/shared/http/types";

type HttpClientErrorOptions = {
  status: number;
  statusText: string;
  url: string;
  payload?: ApiErrorResponse;
};

export class HttpClientError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly url: string;
  readonly code?: string;
  readonly requestId?: string;
  readonly responseMessage?: string;
  readonly details: Array<{ field: string; reason: string }>;

  constructor(options: HttpClientErrorOptions) {
    const message = options.payload
      ? `${options.payload.code}: ${options.payload.message}`
      : `HTTP ${options.status}: ${options.statusText || "Request failed"}`;
    super(message);
    this.name = "HttpClientError";
    this.status = options.status;
    this.statusText = options.statusText;
    this.url = options.url;
    this.code = options.payload?.code;
    this.requestId = options.payload?.request_id;
    this.responseMessage = options.payload?.message;
    this.details = options.payload?.details ?? [];
  }
}

export class HttpNetworkError extends Error {
  readonly url: string;

  constructor(url: string) {
    super("暂时无法连接服务，请检查后端服务状态后重试。");
    this.name = "HttpNetworkError";
    this.url = url;
  }
}

export function toUserErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof HttpClientError) {
    return error.responseMessage || fallback;
  }

  if (error instanceof HttpNetworkError) {
    return error.message;
  }

  return fallback;
}
