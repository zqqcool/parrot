import { Table } from "antd";
import type { TablePaginationConfig, TableProps } from "antd";

import "./data-table.css";

const defaultPagination = {
  pageSizeOptions: ["10", "20", "50", "100"],
  position: ["bottomCenter"],
  showSizeChanger: true,
} satisfies TablePaginationConfig;

export type DataTableProps<RecordType extends object> = TableProps<RecordType>;

export type ParrotDataTableProps<RecordType extends object> = DataTableProps<RecordType> & {
  resetPaginationKey?: string;
};

export function DataTable<RecordType extends object>({
  className,
  pagination,
  resetPaginationKey,
  size = "small",
  ...props
}: ParrotDataTableProps<RecordType>) {
  const resolvedPagination =
    pagination === false ? false : { ...defaultPagination, ...(pagination ?? {}) };
  const tableClassName = ["parrot-data-table", className].filter(Boolean).join(" ");

  return (
    <Table<RecordType>
      {...props}
      className={tableClassName}
      key={resetPaginationKey}
      pagination={resolvedPagination}
      size={size}
    />
  );
}
