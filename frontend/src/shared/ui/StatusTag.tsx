import { Tag } from "antd";
import type { ComponentProps, ReactNode } from "react";

type TagColor = ComponentProps<typeof Tag>["color"];

type StatusTagProps = {
  active: boolean;
  activeLabel: ReactNode;
  inactiveLabel: ReactNode;
  activeColor?: TagColor;
  inactiveColor?: TagColor;
};

export function BinaryStatusTag({
  active,
  activeLabel,
  inactiveLabel,
  activeColor = "success",
  inactiveColor = "default",
}: StatusTagProps) {
  return (
    <Tag color={active ? activeColor : inactiveColor}>{active ? activeLabel : inactiveLabel}</Tag>
  );
}
