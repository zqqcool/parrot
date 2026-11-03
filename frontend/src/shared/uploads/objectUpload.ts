import * as qiniu from "qiniu-js";

export type ObjectUploadGrant = {
  object_key: string;
  upload_key: string;
  upload_token: string;
  expires_at: string;
};

export type ObjectUploadMetadata = {
  content_type: string;
  size_bytes: number;
};

type UploadObjectOptions = {
  file: File;
  contentType?: string;
  onProgress?: (percent: number) => void;
  requestGrant: (metadata: ObjectUploadMetadata) => Promise<ObjectUploadGrant>;
  signal?: AbortSignal;
};

/**
 * Uploads one browser-selected file with a short-lived, exact-key Qiniu upload token.
 * The token remains in memory and is never persisted by this module.
 */
export async function uploadObject({
  file,
  contentType,
  onProgress,
  requestGrant,
  signal,
}: UploadObjectOptions) {
  const resolvedContentType = contentType ?? file.type;
  const grant = await requestGrant({
    content_type: resolvedContentType,
    size_bytes: file.size,
  });
  return new Promise<ObjectUploadGrant>((resolve, reject) => {
    let settled = false;
    const finish = (callback: () => void) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener("abort", abortUpload);
      callback();
    };
    const abortUpload = () => {
      subscription.unsubscribe();
      if (settled) return;
      settled = true;
      signal?.removeEventListener("abort", abortUpload);
      reject(new Error("Upload cancelled"));
    };
    const failUpload = () => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener("abort", abortUpload);
      reject(new Error("Qiniu upload failed"));
    };
    const subscription = qiniu
      .upload(
        file,
        grant.upload_key,
        grant.upload_token,
        { fname: file.name, mimeType: resolvedContentType },
        {
          useCdnDomain: false,
          disableStatisticsReport: true,
        },
      )
      .subscribe({
        next: ({ total }) => onProgress?.(Math.min(100, Math.max(0, total.percent))),
        error: failUpload,
        complete: () =>
          finish(() => {
            onProgress?.(100);
            resolve(grant);
          }),
      });
    signal?.addEventListener("abort", abortUpload, { once: true });
    if (signal?.aborted) abortUpload();
  });
}
