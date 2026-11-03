import type { SkillFileContent } from "@/shared/api/types";

export function updateOpenedChecksums(files: Record<string, SkillFileContent>, checksum: string) {
  return Object.fromEntries(
    Object.entries(files).map(([path, file]) => [path, { ...file, checksum }]),
  );
}

export function withDirtyPath(paths: Set<string>, path: string) {
  return new Set(paths).add(path);
}

export function withoutDirtyPath(paths: Set<string>, path: string) {
  const next = new Set(paths);
  next.delete(path);
  return next;
}

export function withoutDirtyPathPrefix(paths: Set<string>, prefix: string) {
  return new Set([...paths].filter((path) => path !== prefix && !path.startsWith(`${prefix}/`)));
}
