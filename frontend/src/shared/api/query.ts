export function withSearchQuery(path: string, query = ""): string {
  const normalized = query.trim();
  return normalized ? `${path}?${new URLSearchParams({ query: normalized })}` : path;
}
