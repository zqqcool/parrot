import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { DataTable } from "./DataTable";

type Row = { id: string; name: string };

const rows: Row[] = Array.from({ length: 11 }, (_, index) => ({
  id: String(index),
  name: `Row ${index + 1}`,
}));

describe("DataTable", () => {
  it("applies the shared compact, centered, size-selectable pagination defaults", () => {
    const { container } = render(
      <DataTable<Row>
        columns={[{ dataIndex: "name", title: "Name" }]}
        dataSource={rows}
        rowKey="id"
      />,
    );

    expect(container.querySelector(".parrot-data-table")).toBeInTheDocument();
    expect(container.querySelector(".ant-table-small")).toBeInTheDocument();
    expect(container.querySelector(".ant-pagination.ant-pagination-center")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("preserves an explicit pagination opt-out", () => {
    const { container } = render(
      <DataTable<Row>
        columns={[{ dataIndex: "name", title: "Name" }]}
        dataSource={rows}
        pagination={false}
        rowKey="id"
      />,
    );

    expect(container.querySelector(".ant-pagination")).not.toBeInTheDocument();
  });

  it("returns to the first page when a server search result set changes", async () => {
    const user = userEvent.setup();
    const table = (resetPaginationKey: string) => (
      <DataTable<Row>
        columns={[{ dataIndex: "name", title: "Name" }]}
        dataSource={rows}
        resetPaginationKey={resetPaginationKey}
        rowKey="id"
      />
    );
    const { container, rerender } = render(table("all"));

    const secondPage = container.querySelector<HTMLElement>('.ant-pagination-item[title="2"]');
    if (!secondPage) throw new Error("Second table page is missing");
    await user.click(secondPage);
    expect(container).toHaveTextContent("Row 11");

    rerender(table("server-query"));
    expect(container).toHaveTextContent("Row 1");
    expect(container).not.toHaveTextContent("Row 11");
  });
});
