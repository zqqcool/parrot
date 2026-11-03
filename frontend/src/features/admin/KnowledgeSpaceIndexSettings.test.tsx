import { render, screen } from "@testing-library/react";
import { Form } from "antd";
import { expect, it } from "vitest";

import { KnowledgeSpaceIndexSettings } from "@/features/admin/KnowledgeSpaceIndexSettings";

it("uses the full grid column for chunk size fields", () => {
  render(
    <Form>
      <KnowledgeSpaceIndexSettings activeEmbeddings={[]} vectorEnabled={false} />
    </Form>,
  );

  expect(
    screen.getByRole("spinbutton", { name: "单块目标字符数" }).closest(".ant-input-number"),
  ).toHaveStyle({ width: "100%" });
  expect(
    screen.getByRole("spinbutton", { name: "相邻块重叠字符数" }).closest(".ant-input-number"),
  ).toHaveStyle({ width: "100%" });
});
