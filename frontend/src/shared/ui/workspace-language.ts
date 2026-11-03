export function workspaceLanguageFor(path: string) {
  if (path.endsWith(".md")) return "markdown";
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".py")) return "python";
  if (path.endsWith(".yaml") || path.endsWith(".yml")) return "yaml";
  if (path.endsWith(".sh")) return "shell";
  return "plaintext";
}

export function isWorkspaceMarkdown(path: string | undefined) {
  return path?.toLowerCase().endsWith(".md") ?? false;
}
