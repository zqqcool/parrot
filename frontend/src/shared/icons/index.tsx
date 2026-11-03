import {
  AllApplication,
  ApplicationOne,
  ArrowLeft,
  ArrowRight,
  Audit,
  Back,
  Dashboard,
  Delete,
  EditTwo,
  FileAddition,
  FileText,
  Folder,
  FolderPlus,
  FullScreenOne,
  History,
  Lock,
  Logout,
  MenuFold,
  MenuUnfold,
  Message,
  OffScreen,
  People,
  Pin,
  Permissions,
  Plus,
  Refresh,
  RobotOne,
  Search,
  Send,
  SettingTwo,
  Upload,
  User,
  Voice,
  VoiceOff,
  Workbench,
} from "@icon-park/react";

import type { AppIconSize } from "./sizes";

export type { AppIconSize } from "./sizes";

type IconComponent = (props: {
  theme?: "outline" | "filled" | "two-tone" | "multi-color";
  size?: string | number;
  className?: string;
}) => JSX.Element;

const icons = {
  AllApplication,
  ApplicationOne,
  ArrowLeft,
  ArrowRight,
  Audit,
  Back,
  Dashboard,
  Delete,
  EditTwo,
  FileAddition,
  FileText,
  Folder,
  FolderPlus,
  FullScreenOne,
  History,
  Lock,
  Logout,
  MenuFold,
  MenuUnfold,
  Message,
  OffScreen,
  People,
  Pin,
  Permissions,
  Plus,
  Refresh,
  RobotOne,
  Search,
  Send,
  SettingTwo,
  Upload,
  User,
  Voice,
  VoiceOff,
  Workbench,
} satisfies Record<string, IconComponent>;

export type AppIconName = keyof typeof icons;

type IconProps = {
  name: AppIconName;
  size?: AppIconSize;
  className?: string;
  theme?: "outline" | "filled" | "two-tone" | "multi-color";
};

export function AppIcon({ name, size = "md", className, theme = "outline" }: IconProps) {
  const Icon = icons[name];
  const classes = ["parrot-icon", `parrot-icon--${size}`, className].filter(Boolean).join(" ");

  return (
    <span aria-hidden="true" className={classes} data-icon={name}>
      <Icon theme={theme} size="1em" />
    </span>
  );
}
