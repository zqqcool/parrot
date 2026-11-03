import type { DownloadedFile } from "@/shared/http";

export function saveDownloadedFile(file: DownloadedFile): void {
  const objectUrl = URL.createObjectURL(file.blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = file.filename;
  link.rel = "noopener";
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}
