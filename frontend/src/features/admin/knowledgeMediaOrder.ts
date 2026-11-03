import type { KnowledgeMediaRef } from "@/shared/api/types";

export function orderMediaRefs(refs: readonly KnowledgeMediaRef[]): KnowledgeMediaRef[] {
  return [...refs].sort((left, right) => {
    const locatorDelta = mediaSortKey(left).localeCompare(mediaSortKey(right), "zh-CN", {
      numeric: true,
    });
    if (locatorDelta !== 0) return locatorDelta;
    return left.ordinal - right.ordinal;
  });
}

export function mediaRefLabel(ref: KnowledgeMediaRef): string {
  if (ref.slide_no != null) {
    const suffix = ref.asset_kind === "thumb" ? "（降级预览）" : "";
    return `第 ${ref.slide_no} 页${suffix}`;
  }
  if (ref.cell_anchor) return ref.cell_anchor;
  if (ref.sheet_name) return `工作表 ${ref.sheet_name}`;
  if (ref.section_path) return `章节 ${ref.section_path}`;
  return ref.asset_kind === "thumb" ? "降级预览图" : "预览图";
}

export function mediaGroupLabel(
  slideNo: number | null | undefined,
  refs: readonly KnowledgeMediaRef[],
): string {
  const slides = unique(refs.map((ref) => ref.slide_no)).sort((left, right) => left - right);
  if (slides.length > 1) return `关联幻灯片 ${slides.join(" · ")}`;
  if (slides.length === 1) return `幻灯片 ${slides[0]}`;
  if (slideNo != null) return `幻灯片 ${slideNo}`;
  const sheets = unique(refs.map((ref) => ref.sheet_name));
  if (sheets.length > 0) return `关联工作表 ${sheets.join(" · ")}`;
  const sections = unique(refs.map((ref) => ref.section_path));
  if (sections.length > 0) return `关联章节 ${sections.join(" · ")}`;
  return "关联图";
}

function mediaSortKey(ref: KnowledgeMediaRef): string {
  if (ref.slide_no != null) return `0:${String(ref.slide_no).padStart(8, "0")}`;
  if (ref.sheet_name) return `1:${ref.sheet_name}:${ref.cell_anchor ?? ""}`;
  if (ref.section_path) return `2:${ref.section_path}`;
  return "3";
}

function unique<T>(values: Array<T | null | undefined>): T[] {
  return [...new Set(values.filter((value): value is T => value != null))];
}
