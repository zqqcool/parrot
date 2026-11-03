import { useId, useState, type ReactNode } from "react";
import { Button, Input } from "antd";

import { AppIcon } from "@/shared/icons";

import "./search-bar.css";

type SearchBarProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  advancedFilters?: ReactNode;
  hasActiveFilters?: boolean;
  onReset?: () => void;
  actions?: ReactNode;
};

export function SearchBar({
  value,
  onChange,
  placeholder = "搜索",
  advancedFilters,
  hasActiveFilters = false,
  onReset,
  actions,
}: SearchBarProps) {
  const [expanded, setExpanded] = useState(false);
  const panelId = useId();

  return (
    <div className="parrot-search-bar">
      <div className="parrot-search-bar-main">
        <SearchControls
          expanded={expanded}
          hasActiveFilters={hasActiveFilters}
          onChange={onChange}
          onReset={onReset}
          panelId={panelId}
          placeholder={placeholder}
          showAdvancedFilters={Boolean(advancedFilters)}
          value={value}
          onToggle={() => setExpanded((current) => !current)}
        />
        <div className="parrot-search-bar-actions">{actions}</div>
      </div>
      <AdvancedFilters expanded={expanded} filters={advancedFilters} panelId={panelId} />
    </div>
  );
}

type SearchControlsProps = Pick<
  SearchBarProps,
  "hasActiveFilters" | "onChange" | "onReset" | "placeholder" | "value"
> & {
  expanded: boolean;
  panelId: string;
  showAdvancedFilters: boolean;
  onToggle: () => void;
};

function SearchControls({
  expanded,
  hasActiveFilters = false,
  onChange,
  onReset,
  panelId,
  placeholder = "搜索",
  showAdvancedFilters,
  value,
  onToggle,
}: SearchControlsProps) {
  const canReset = Boolean(onReset && (value || hasActiveFilters));
  return (
    <div className="parrot-search-bar-controls">
      <Input
        allowClear
        aria-label={placeholder}
        maxLength={300}
        placeholder={placeholder}
        prefix={<AppIcon name="Search" size="sm" />}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      {showAdvancedFilters ? (
        <Button aria-controls={panelId} aria-expanded={expanded} onClick={onToggle}>
          {expanded ? "收起筛选" : "更多筛选"}
        </Button>
      ) : null}
      {onReset ? (
        <Button disabled={!canReset} onClick={onReset}>
          重置
        </Button>
      ) : null}
    </div>
  );
}

function AdvancedFilters({
  expanded,
  filters,
  panelId,
}: {
  expanded: boolean;
  filters: ReactNode;
  panelId: string;
}) {
  if (!filters) return null;
  return (
    <div
      aria-hidden={!expanded}
      className={`parrot-search-bar-advanced${expanded ? " is-expanded" : ""}`}
      id={panelId}
    >
      <div className="parrot-search-bar-advanced-content">{filters}</div>
    </div>
  );
}
