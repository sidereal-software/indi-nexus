/**
 * The two `DEVIATION`s in `ui/sidebar.tsx`, held in place by tests.
 *
 * `src/ui/` is vendored from the shadcn registry and is not hand-edited, with
 * exactly two exceptions - and this file covers one of them. That makes these
 * tests something more than coverage: a `shadcn add sidebar` re-fetches the
 * registry file and silently drops both corrections, and each is *behaviour*
 * that no stylesheet can reach, so nothing else in the suite would notice. They
 * are written to fail loudly in that case.
 *
 * The two, in the file's own numbering:
 *
 * 1. **Focus restoration.** The drawer is a Sheet with no `Dialog.Trigger`, so
 *    Radix's close handler prevents FocusScope's restore and then focuses a
 *    `triggerRef` that is `null` - landing the keyboard on `<body>` and
 *    restarting the tab order at the top of the document (SC 2.4.3).
 * 2. **The tooltip that ate Escape.** A hidden tooltip is still an *open*
 *    dismissable layer above the drawer's, so the first Escape closed something
 *    invisible and the drawer needed a second.
 *
 * There used to be a third, and its removal is why the last `describe` here is
 * not named for one. The registry hides the drawer's close button with
 * `[&>button]:hidden`, leaving Escape and an overlay tap as the only ways out of
 * an 18rem drawer - on a device with no Escape key, whose overlay is
 * `aria-hidden`. That one *is* reachable from CSS: the utility compiles into
 * `@layer utilities`, so an unlayered `display: revert` in `theme.css` outranks
 * it, and the vendored file went back to registry-exact on that line. What is
 * left here is the half jsdom can still witness - that the selector both
 * corrections hang off still finds the close button.
 *
 * The reproduction was at 390x844; here `useIsMobile` is driven by a stubbed
 * `matchMedia` and `innerWidth`, as `use-mobile.test.ts` does.
 */

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  Sidebar,
  SidebarContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/ui/sidebar";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  // Radix defers both its outside-pointer listener and FocusScope's restore by a
  // task, so the whole file runs on fake timers and flushes them by hand rather
  // than waiting on a wall clock.
  vi.useFakeTimers();
});

/**
 * Report a viewport of the given width to `useIsMobile`.
 *
 * @param width - CSS pixels; below 768 is the drawer, at or above it the rail.
 */
function stubViewport(width: number): void {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: width < 768,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
  vi.stubGlobal("innerWidth", width);
}

/**
 * Let Radix's deferred work run: the dismiss listeners and the focus restore.
 *
 * Deferred in layers - the outside-pointer dismiss is scheduled by a click
 * handler, and FocusScope's restore is scheduled by the unmount that dismiss
 * causes - so this drains the queue rather than advancing it a fixed number of
 * times, and never waits on a wall clock.
 */
function flushDeferred(): void {
  act(() => {
    for (let pass = 0; pass < 10 && vi.getTimerCount() > 0; pass += 1) {
      vi.runOnlyPendingTimers();
    }
  });
}

/**
 * A sidebar with one device in it, plus the trigger that opens it.
 *
 * The trigger deliberately renders *outside* the sidebar, which is the whole
 * reason DEVIATION 1 exists: there is no `Dialog.Trigger` for Radix to restore
 * focus to.
 *
 * @param open - Whether the desktop sidebar starts expanded.
 * @returns The render result.
 */
function renderSidebar(open = true) {
  return render(
    <SidebarProvider defaultOpen={open}>
      <SidebarTrigger />
      <Sidebar>
        <SidebarContent>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton tooltip="CCD Simulator">CCD Simulator</SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarContent>
      </Sidebar>
    </SidebarProvider>,
  );
}

/**
 * The trigger button, which is also what focus has to come back to.
 *
 * @returns The trigger.
 */
function trigger(): HTMLElement {
  return screen.getByRole("button", { name: "Toggle Sidebar" });
}

/**
 * Focus the trigger and press it, the way a keyboard user opens the drawer.
 *
 * Focused for real rather than merely clicked, because what the deviation
 * restores is `document.activeElement` at the moment the drawer opened.
 *
 * @returns The element focus has to return to.
 */
function openDrawerFromTrigger(): HTMLElement {
  const button = trigger();
  button.focus();
  expect(document.activeElement).toBe(button);
  fireEvent.click(button);
  flushDeferred();
  return button;
}

/**
 * The open mobile drawer.
 *
 * @returns The drawer's dialog element.
 */
function drawer(): HTMLElement {
  return screen.getByRole("dialog");
}

/**
 * Every tooltip body mounted anywhere in the document.
 *
 * Counted rather than queried by role, because the registry's bug is a tooltip
 * that is mounted and *hidden*: `getByRole("tooltip")` cannot see it, and it is
 * still an open dismissable layer above the drawer's, which is the whole defect.
 *
 * @returns Every mounted tooltip body, visible or not.
 */
function mountedTooltips(): NodeListOf<Element> {
  return document.querySelectorAll('[data-slot="tooltip-content"]');
}

describe("the mobile drawer restores focus to its opener (DEVIATION 1)", () => {
  beforeEach(() => {
    stubViewport(390);
  });

  it("puts focus back on the trigger when Escape closes the drawer", () => {
    renderSidebar();
    const opener = openDrawerFromTrigger();
    expect(drawer()).toBeInTheDocument();

    fireEvent.keyDown(drawer(), { key: "Escape" });
    flushDeferred();

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // Without the deviation this is `<body>`, and the next Tab restarts the tab
    // order at the top of the document instead of continuing from the control
    // the operator was on.
    expect(document.activeElement).toBe(opener);
  });

  it("puts focus back on the trigger when a tap on the overlay closes the drawer", () => {
    renderSidebar();
    const opener = openDrawerFromTrigger();
    const overlay = document.querySelector('[data-slot="sheet-overlay"]');
    if (overlay === null) throw new Error("the drawer rendered no overlay");

    // Both halves of a tap: Radix defers the outside dismiss from the
    // `pointerdown` to the `click` that follows it.
    fireEvent.pointerDown(overlay);
    fireEvent.click(overlay);
    flushDeferred();

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(opener);
  });

  it("puts focus back on the trigger when the drawer's own close button closes it", () => {
    renderSidebar();
    const opener = openDrawerFromTrigger();

    fireEvent.click(within(drawer()).getByRole("button", { name: "Close" }));
    flushDeferred();

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(opener);
  });
});

describe("the close button theme.css un-hides and grows", () => {
  beforeEach(() => {
    stubViewport(390);
  });

  it("renders a close button inside the drawer", () => {
    // A phone has no Escape key, and the overlay is `aria-hidden` and so
    // unreachable by a VoiceOver swipe: with this hidden there is no way out of
    // an 18rem drawer that assistive technology can find at all.
    renderSidebar();
    openDrawerFromTrigger();
    expect(within(drawer()).getByRole("button", { name: "Close" })).toBeInTheDocument();
  });

  it("matches the selector theme.css un-hides and grows to a 44px target", () => {
    // The drawer spreads `data-slot="sidebar"` over the primitive's own
    // `sheet-content`, so the sheet's own target-size hook never sees it and
    // `[data-mobile="true"]` is what reaches this close and nothing else. It
    // carries both corrections: the registry's `[&>button]:hidden` is still on
    // the drawer and `display: revert` is what beats it.
    //
    // Neither correction is observable here - jsdom loads no stylesheet, so a
    // `toBeVisible()` above would pass with the button still hidden in every
    // browser. The rules' existence and their standing outside every cascade
    // layer are `theme-cascade.test.ts`; that they still have an element to
    // match is this.
    renderSidebar();
    openDrawerFromTrigger();
    const corrected = document.querySelector(
      '[data-mobile="true"] > [class~="ring-offset-background"]',
    );
    expect(corrected).toBe(within(drawer()).getByRole("button", { name: "Close" }));
  });
});

describe("the tooltip that ate Escape (DEVIATION 2)", () => {
  it("closes the mobile drawer on the first Escape, with a menu button focused", () => {
    // The reproduction: focusing the button opened a tooltip that had nothing to
    // show, and a hidden tooltip is still an open dismissable layer sitting above
    // the drawer's - so the first Escape dismissed something nobody could see.
    stubViewport(390);
    renderSidebar();
    openDrawerFromTrigger();
    const menuButton = within(drawer()).getByRole("button", { name: "CCD Simulator" });
    act(() => menuButton.focus());
    flushDeferred();

    fireEvent.keyDown(menuButton, { key: "Escape" });
    flushDeferred();

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("mounts no tooltip around a menu button in the drawer", () => {
    stubViewport(390);
    renderSidebar();
    openDrawerFromTrigger();
    const menuButton = within(drawer()).getByRole("button", { name: "CCD Simulator" });
    act(() => menuButton.focus());
    flushDeferred();

    // Not mounted, rather than mounted invisible. The button's own attributes
    // cannot tell the two apart - `asChild` leaves the child's `data-slot` on
    // the element either way - so this counts the layers instead.
    expect(mountedTooltips()).toHaveLength(0);
    expect(menuButton).toHaveAccessibleName("CCD Simulator");
  });

  it("mounts no tooltip on the expanded desktop sidebar either", () => {
    // Nothing to say: the label is already beside the icon.
    stubViewport(1024);
    renderSidebar(true);
    const menuButton = screen.getByRole("button", { name: "CCD Simulator" });
    act(() => menuButton.focus());
    flushDeferred();

    expect(mountedTooltips()).toHaveLength(0);
  });

  it("still shows a real tooltip on the collapsed desktop rail", () => {
    // The other half of the deviation, and the reason it is "not mounted" rather
    // than "removed": collapsed to icons, the tooltip is the only label there is.
    stubViewport(1024);
    renderSidebar(false);
    const menuButton = screen.getByRole("button", { name: "CCD Simulator" });
    act(() => menuButton.focus());
    flushDeferred();

    expect(screen.getByRole("tooltip")).toHaveTextContent("CCD Simulator");
  });
});
