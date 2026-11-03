import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppIcon } from "./index";

describe("AppIcon", () => {
  it("renders a normalized decorative icon box with the default semantic size", () => {
    const { container } = render(<AppIcon name="Refresh" />);
    const icon = container.querySelector(".parrot-icon");

    expect(icon).toHaveClass("parrot-icon--md");
    expect(icon).toHaveAttribute("aria-hidden", "true");
    expect(icon).toHaveAttribute("data-icon", "Refresh");
    expect(icon?.querySelector("svg")).toHaveAttribute("width", "1em");
  });

  it("keeps caller classes while using the requested semantic size", () => {
    const { container } = render(<AppIcon className="test-icon" name="History" size="lg" />);

    expect(container.querySelector(".parrot-icon")).toHaveClass("parrot-icon--lg", "test-icon");
  });

  it("supports the selected IconPark visual theme", () => {
    const { container } = render(<AppIcon name="Back" theme="filled" />);

    expect(container.querySelector(".parrot-icon")).toHaveAttribute("data-icon", "Back");
  });
});
