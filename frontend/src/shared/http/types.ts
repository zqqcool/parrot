export type ApiResponse<T> = {
  code: string;
  message: string;
  data: T;
  request_id: string;
};

export type ApiErrorResponse = {
  code: string;
  message: string;
  details: Array<{ field: string; reason: string }>;
  request_id: string;
};

export type HttpRequestOptions = {
  requestId?: string;
  idempotencyKey?: string | true;
  signal?: AbortSignal;
  timeoutMs?: number;
};

export type DownloadedFile = {
  blob: Blob;
  filename: string;
};
