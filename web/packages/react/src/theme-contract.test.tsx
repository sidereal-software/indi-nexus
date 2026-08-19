/**
 * The class hooks `theme.css` corrects the vendored primitives through.
 *
 * The corrections at the bottom of `theme.css` are keyed on the utility class
 * the shadcn registry emits, not on `data-slot`, because `data-slot` does not
 * survive `asChild`. That makes the class list a contract between two files that
 * nothing else checks: a `shadcn add button` that renamed
 * `focus-visible:ring-ring/50` would leave the theme matching nothing at all, and
 * every other test in this package would still pass. This file is that check.
 *
 * It asserts what renders, not what the browser then computes with it -
 * `theme-cascade.test.ts` is the half that compiles.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cwd } from "node:process";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/ui/accordion";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from "@/ui/alert-dialog";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/ui/dialog";
import { Input } from "@/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/ui/sheet";
import { Switch } from "@/ui/switch";
import { Toggle } from "@/ui/toggle";
import { Tooltip, TooltipProvider, TooltipTrigger } from "@/ui/tooltip";
import { MessageLog } from "./components/message-log";
import { renderConnected } from "./testing/render";

afterEach(cleanup);

/** The stylesheet under test, read from source rather than from the build. */
const themeCss = readFileSync(join(cwd(), "src/theme.css"), "utf8");

/**
 * The selector of the rule containing a declaration.
 *
 * `theme.css` is hand-formatted with each selector and its opening brace on one
 * line, so the line above the brace is the selector.
 *
 * @param declaration - Literal declaration text to find, e.g. `animation: x`.
 * @returns The selector of the rule that declaration sits in.
 */
function ruleSelectorFor(declaration: string): string {
  const index = themeCss.indexOf(declaration);
  if (index === -1) throw new Error(`no \`${declaration}\` in theme.css`);
  const open = themeCss.lastIndexOf("{", index);
  return themeCss.slice(themeCss.lastIndexOf("\n", open) + 1, open).trim();
}

/**
 * The body of an at-rule or ruleset, by brace matching from its prelude.
 *
 * @param prelude - Literal text opening the block, e.g. `@keyframes state-pulse`.
 * @returns Everything between the block's outermost braces.
 */
function blockBody(prelude: string): string {
  const start = themeCss.indexOf(prelude);
  if (start === -1) throw new Error(`no \`${prelude}\` in theme.css`);
  const open = themeCss.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < themeCss.length; i += 1) {
    if (themeCss[i] === "{") depth += 1;
    else if (themeCss[i] === "}") {
      depth -= 1;
      if (depth === 0) return themeCss.slice(open + 1, i);
    }
  }
  throw new Error(`unbalanced braces after \`${prelude}\``);
}

describe("the focus-ring hook", () => {
  it.each([
    ["Button", <Button key="b">Set</Button>, "button"],
    ["Input", <Input key="i" aria-label="value" />, "input"],
    ["Switch", <Switch key="s" aria-label="debug" />, "switch"],
    ["Toggle", <Toggle key="t">On</Toggle>, "toggle"],
    ["Badge", <Badge key="g">Ok</Badge>, "badge"],
  ])("survives on %s", (_name, element, slot) => {
    const { container } = render(element);
    const node = container.querySelector(`[data-slot="${slot}"]`);
    expect(node).not.toBeNull();
    expect(node).toHaveClass("focus-visible:ring-ring/50");
  });

  it("survives on AccordionTrigger", () => {
    render(
      <Accordion type="single" collapsible defaultValue="only">
        <AccordionItem value="only">
          <AccordionTrigger>Driver internals</AccordionTrigger>
          <AccordionContent>nothing here</AccordionContent>
        </AccordionItem>
      </Accordion>,
    );
    expect(screen.getByRole("button", { name: "Driver internals" })).toHaveClass(
      "focus-visible:ring-ring/50",
    );
  });

  it("survives on the message log's scrolling viewport", () => {
    // The one focusable element in the theme that is not a control: `ScrollArea`
    // puts the class on the viewport, which is why the DEVIATION in
    // `ui/scroll-area.tsx` exists at all.
    renderConnected(<MessageLog />);
    expect(screen.getByRole("log", { name: "INDI messages" })).toHaveClass(
      "focus-visible:ring-ring/50",
    );
  });

  it("survives a Tooltip-wrapped Button, where data-slot does not", () => {
    render(
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="secondary">Set</Button>
          </TooltipTrigger>
        </Tooltip>
      </TooltipProvider>,
    );
    const trigger = screen.getByRole("button", { name: "Set" });
    // The Slot merges the child's props over the parent's, so the primitive's own
    // slot name is what is left on the element - and the class lists concatenate.
    expect(trigger).toHaveAttribute("data-slot", "tooltip-trigger");
    expect(trigger).toHaveClass("focus-visible:ring-ring/50");
    expect(trigger).toHaveClass("hover:bg-secondary/80");
  });
});

describe("the destructive focus-ring hook", () => {
  it("survives on AlertDialogAction, which is the button it exists for", () => {
    render(
      <AlertDialog open>
        <AlertDialogContent>
          <AlertDialogTitle>Delete saved config?</AlertDialogTitle>
          <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
          <AlertDialogAction variant="destructive">Delete saved config</AlertDialogAction>
        </AlertDialogContent>
      </AlertDialog>,
    );
    const action = screen.getByRole("button", { name: "Delete saved config" });
    expect(action).toHaveClass("focus-visible:ring-destructive/20");
    // The assertion that stops the next reader re-proposing a `data-slot` hook:
    // this IS the button, and its slot name is not `button`.
    expect(action).not.toHaveAttribute("data-slot", "button");
    expect(action).toHaveAttribute("data-slot", "alert-dialog-action");
  });
});

describe("the target-size hooks", () => {
  it("renders the switch slot the overlay is anchored on", () => {
    const { container } = render(<Switch aria-label="debug" />);
    expect(container.querySelector('[data-slot="switch"]')).not.toBeNull();
  });

  it("renders the accordion-content slot the reduced-motion rule names", () => {
    const { container } = render(
      <Accordion type="single" collapsible defaultValue="only">
        <AccordionItem value="only">
          <AccordionTrigger>Driver internals</AccordionTrigger>
          <AccordionContent>nothing here</AccordionContent>
        </AccordionItem>
      </Accordion>,
    );
    expect(container.querySelector('[data-slot="accordion-content"]')).not.toBeNull();
  });

  it("keeps the dialog close a direct child of the content slot", () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Configuration</DialogTitle>
          <DialogDescription>Actions for this device.</DialogDescription>
        </DialogContent>
      </Dialog>,
    );
    // The exact selector `theme.css` uses. `ui/sheet.tsx` gives its close no
    // `data-slot` at all, so parent slot plus class token is the only hook that
    // covers both, and this is the only coverage either one has.
    expect(
      document.querySelector('[data-slot="dialog-content"] > [class~="ring-offset-background"]'),
    ).not.toBeNull();
  });

  it("keeps the sheet close a direct child of the content slot", () => {
    render(
      <Sheet open>
        <SheetContent>
          <SheetTitle>Sidebar</SheetTitle>
          <SheetDescription>Displays the mobile sidebar.</SheetDescription>
        </SheetContent>
      </Sheet>,
    );
    expect(
      document.querySelector('[data-slot="sheet-content"] > [class~="ring-offset-background"]'),
    ).not.toBeNull();
  });
});

describe("the busy pulse", () => {
  it("animates nothing that carries the badge's contrast", () => {
    // The whole reason the pulse is a ring: `animate-pulse` fades the element to
    // 0.5, which takes the label down with the fill (1.75:1 at the dimmest
    // frame). Only `transform` and `opacity` may appear here, and both act on a
    // pseudo-element rather than on the badge.
    const properties = new Set(
      [...blockBody("@keyframes state-pulse").matchAll(/([a-z-]+)\s*:/g)].map((match) => match[1]),
    );
    expect([...properties].sort()).toEqual(["opacity", "transform"]);
  });

  it("applies the animation to a pseudo-element, not to the badge", () => {
    expect(ruleSelectorFor("animation: state-pulse")).toBe("[data-indi-pulse]::after");
  });
});
