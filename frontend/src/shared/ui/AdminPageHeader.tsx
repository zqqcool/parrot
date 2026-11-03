import { Breadcrumb, Button } from "antd";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { AppIcon } from "@/shared/icons";

type BreadcrumbItem = { title: ReactNode };

type AdminPageHeaderProps = {
  title: string;
  description?: string;
  action?: ReactNode;
  breadcrumbs?: BreadcrumbItem[];
  compact?: boolean;
};

export function AdminPageHeader({
  title,
  description,
  action,
  breadcrumbs,
  compact = false,
}: AdminPageHeaderProps) {
  return (
    <header
      className={compact ? "admin-page-header admin-page-header-compact" : "admin-page-header"}
    >
      <Breadcrumb items={breadcrumbs ?? [{ title: <Link to="/admin">工作台</Link> }, { title }]} />
      <div className="admin-page-heading">
        <div>
          <h1>{title}</h1>
          {description ? <p>{description}</p> : null}
        </div>
        {action}
      </div>
    </header>
  );
}

export function CreateButton({
  children = "新建",
  onClick,
}: {
  children?: ReactNode;
  onClick: () => void;
}) {
  return (
    <Button type="primary" icon={<AppIcon name="Plus" size="md" />} onClick={onClick}>
      {children}
    </Button>
  );
}
