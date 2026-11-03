const contentTypesByExtension = {
  ".pdf": "application/pdf",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ".md": "text/markdown",
  ".txt": "text/plain",
} as const;

export const knowledgeUploadAccept = Object.keys(contentTypesByExtension).join(",");

export function knowledgeUploadContentType(fileName: string): string | null {
  const extension = fileName.slice(fileName.lastIndexOf(".")).toLowerCase();
  return contentTypesByExtension[extension as keyof typeof contentTypesByExtension] ?? null;
}

export function knowledgeDocumentTitleFromFile(fileName: string): string {
  const extensionIndex = fileName.lastIndexOf(".");
  return extensionIndex > 0 ? fileName.slice(0, extensionIndex) : fileName;
}
