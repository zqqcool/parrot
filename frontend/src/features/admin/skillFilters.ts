import type { Skill } from "@/shared/api/types";

export type SkillStatusFilter = "all" | "published" | "draft" | "disabled";

export function filterSkills(skills: Skill[], statusFilter: SkillStatusFilter): Skill[] {
  return skills.filter((skill) => statusFilter === "all" || skill.status === statusFilter);
}
