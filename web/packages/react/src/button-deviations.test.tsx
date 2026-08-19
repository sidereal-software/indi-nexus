/**
 * The one deviation `ui/button.tsx` carries from the shadcn registry.
 *
 * `src/ui/` is vendored and is not hand-edited, with the exception the workspace
 * documents: behaviour a stylesheet cannot reach. This is one of those, and the
 * test exists because a `shadcn add button` would silently put the registry's
 * line back and nothing else in the suite would notice.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Button } from "./ui/button";

afterEach(cleanup);

describe("the destructive Button's deviation", () => {
  it("fills with the destructive token itself, never a tint of it", () => {
    // The registry draws the dark destructive at `bg-destructive/60`. That
    // composite is the defect CONCERNS.md recorded: #973030 at 2.48:1 under the
    // palette before this one, and #7a1719 at 1.75:1 under this one - the most
    // dangerous button in the product reading weakest in the scheme an operator
    // uses at night. `--destructive` is now chosen for the job directly.
    render(<Button variant="destructive">Delete saved config</Button>);
    const button = screen.getByRole("button", { name: "Delete saved config" });

    expect(button.className).toContain("bg-destructive");
    expect(button.className).not.toContain("dark:bg-destructive/60");
    // Any alpha on the fill reintroduces the same failure at a different value,
    // so the assertion is on the class of bug rather than on one number.
    expect(button.className).not.toMatch(/dark:bg-destructive\/\d+/);
  });

  it("keeps the registry's hover and invalid-state hooks", () => {
    // The deviation is one class removed, not a rewrite: everything else the
    // variant carries has to survive, or this stops being a deviation and
    // becomes a fork.
    render(<Button variant="destructive">Delete saved config</Button>);
    const button = screen.getByRole("button", { name: "Delete saved config" });

    expect(button.className).toContain("hover:bg-destructive/90");
    expect(button.className).toContain("focus-visible:ring-destructive/20");
    expect(button.className).toContain("dark:focus-visible:ring-destructive/40");
  });
});
