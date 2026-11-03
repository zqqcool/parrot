import type { Rule } from "antd/es/form";

export function passwordRules(minimumLength: number | undefined): Rule[] {
  return [
    { required: true, message: "请输入密码" },
    ...(minimumLength ? [{ min: minimumLength, message: `密码至少 ${minimumLength} 个字符` }] : []),
  ];
}

export function passwordHint(minimumLength: number | undefined): string | undefined {
  return minimumLength ? `至少 ${minimumLength} 个字符` : undefined;
}
