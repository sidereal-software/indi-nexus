/**
 * The reference INDIkit panel.
 *
 * Everything here is composed from `@indikit/react`: the `IndiProvider` (which
 * connects to the bridge at `/ws`), the hooks, the INDI-aware components, and the
 * themed shadcn primitives. It doubles as a worked example of "build your own UI
 * on the library".
 */

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
  Badge,
  Button,
  ConnectionStatus,
  DeviceConfigDialog,
  DevicePanel,
  DisplaySettingsProvider,
  type IndiClient,
  IndiProvider,
  Label,
  MessageLog,
  Separator,
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  StatusAnnouncer,
  Switch,
  Toaster,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
  useDevices,
  useIndiClient,
  useProperty,
} from "@indikit/react";
import { MessageSquareText, Moon, MoonStar, Radio, Sun, Telescope } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTheme } from "./use-theme";

/** localStorage key remembering whether the messages panel is open. */
const MESSAGES_KEY = "indi-messages";

/**
 * Maximum messages the panel shows: the client's whole rolling buffer
 * (`messageLogLimit`, which itself covers the bridge's 100-message replay for a
 * freshly opened page). Older history belongs to the server logs, not a UI
 * strip, and 200 compact rows keep the DOM light.
 */
const MESSAGE_LIMIT = 200;

/** localStorage key remembering whether debug info (raw INDI names) shows. */
const DEBUG_KEY = "indi-debug";

/** Whether the messages panel should start open (persisted; default open). */
function initialMessagesOpen(): boolean {
  try {
    return localStorage.getItem(MESSAGES_KEY) !== "closed";
  } catch {
    return true;
  }
}

/** Whether debug info should start enabled (persisted; default off). */
function initialDebug(): boolean {
  try {
    return localStorage.getItem(DEBUG_KEY) === "on";
  } catch {
    return false;
  }
}

/**
 * What each scheme is called where an operator reads it, and what comes next.
 *
 * The label says what pressing the control *does*, not what is currently on,
 * because the button is an action - and with three schemes "Toggle theme" stops
 * being true. `night` is named for the thing it actually delivers: it is a
 * luminance-capped scheme meant to be read with the display dimmed, and calling
 * it "night vision" would promise dark adaptation that no readable screen keeps.
 */
const THEMES = {
  light: { icon: Moon, next: "dark", label: "Switch to dark" },
  dark: { icon: MoonStar, next: "night", label: "Switch to dimmed night" },
  night: { icon: Sun, next: "light", label: "Switch to light" },
} as const;

/** An icon button cycling light -> dark -> dimmed night. */
function ThemeToggle() {
  const { theme, cycle } = useTheme();
  const { icon: Icon, label } = THEMES[theme];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {/* SC 2.5.5 wants 44x44. `size-11` is the real box, not an overlay, so
            the hover tint and the focus ring grow with the target; twMerge drops
            the variant's own `size-9`. The icon stays `size-4`. */}
        <Button variant="ghost" size="icon" className="size-11" onClick={cycle} aria-label={label}>
          <Icon />
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

/** The left sidebar: brand, connection state, device list, settings. */
function DeviceSidebar({
  devices,
  active,
  onSelect,
  debug,
  onDebugChange,
}: {
  devices: readonly string[];
  active: string | null;
  onSelect: (device: string) => void;
  debug: boolean;
  onDebugChange: (on: boolean) => void;
}) {
  // Asked here as well as inside the dialog, so the group around it can be
  // absent rather than empty. `useProperty` is a hook and cannot be called
  // conditionally, so a null selection is asked about as the empty device -
  // which no device answers to.
  const hasConfig = useProperty(active ?? "", "CONFIG_PROCESS") !== undefined;
  return (
    <Sidebar>
      <SidebarHeader className="gap-3 p-3 pt-[calc(0.75rem_+_env(safe-area-inset-top))]">
        <div className="flex items-center gap-2">
          <Telescope className="size-5 text-primary" />
          {/* The wordmark separates its halves by weight, not by hue. `kit` used
              to be `text-primary`, which worked while the brand had a colour;
              the theme now spends none, so a coloured wordmark would be the one
              exception to the rule that hue on this screen means instrument
              state - and an exception in the corner of every page is not a rule.
              400 against 700 rather than a subtler step: nothing here declares
              an @font-face, so this renders in whatever mono the machine falls
              back to, and a fallback may synthesise the weight it lacks. */}
          <span className="text-sm">
            <span className="font-normal">INDI</span>
            <span className="font-bold">kit</span>
          </span>
        </div>
        <ConnectionStatus />
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          {/* The primitive labels its groups with `text-sidebar-foreground/70`,
              which measures 6.29:1 in light mode and 5.61:1 in dark - AA, but
              short of the AAA tier DESIGN.md puts secondary text on and this
              label is body-size secondary text. `text-muted-foreground` is that
              tier (7.63 light, 8.64 dark on the sidebar) and twMerge drops the
              primitive's own colour for it. Fixed here rather than in
              `theme.css`: `color` is a real property, so an unlayered correction
              would beat every state variant of it, and this label is one the app
              composes and can therefore reach directly. */}
          <SidebarGroupLabel className="text-muted-foreground">Devices</SidebarGroupLabel>
          <SidebarGroupContent>
            {/* The sidebar's own markup is all `div`s, so without this the device
                list - the page's only means of moving between devices - sits
                outside every landmark and a landmark walk finds only the main
                region and the messages strip. */}
            <nav aria-label="Devices">
              {/* The empty state is a sentence, not a list, and it used to be a
                  `<p>` directly inside `SidebarMenu`'s `<ul>`, where the only
                  legal children are `<li>`. Rendering the list only when there
                  is a list keeps the markup honest without wrapping prose in a
                  menu item; `DeviceConfigDialog` needs no separate guard,
                  because nothing can be selected while nothing is connected. */}
              {devices.length === 0 ? (
                <p className="px-2 py-1.5 text-xs text-muted-foreground">No devices connected.</p>
              ) : (
                <SidebarMenu>
                  {devices.map((device) => (
                    <SidebarMenuItem key={device}>
                      <SidebarMenuButton
                        isActive={device === active}
                        onClick={() => onSelect(device)}
                        tooltip={device}
                      >
                        <Radio />
                        <span>{device}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              )}
            </nav>
          </SidebarGroupContent>
        </SidebarGroup>
        {/* Configuration acts *on* the selected device; it is not one. It used to
            be the last `<li>` of the menu above, which put it inside
            `nav aria-label="Devices"` - so it read as a third device to a sighted
            operator and was announced as one inside the Devices landmark. Its own
            group, with its own heading, says what it is in both directions.

            The group is rendered only when the selected device actually has
            CONFIG_PROCESS. `DeviceConfigDialog` already declines to render
            without it, but an absent dialog inside a present group leaves a
            labelled, empty section - which is worse than the entry it replaced.
            Every libindi driver publishes the property; the demo's dome does not,
            which is exactly the case that would show the hole. */}
        {hasConfig ? (
          <SidebarGroup>
            {/* The heading is the device's own name rather than "Configuration"
                or "Selected device": what an operator needs to know before
                pressing anything here is *whose* configuration this is, and
                every action behind it writes one device's file. It truncates
                because a device name is the driver's to choose. */}
            <SidebarGroupLabel className="truncate text-muted-foreground">
              {active}
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                <DeviceConfigDialog device={active} />
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ) : null}
      </SidebarContent>
      {/* Both footer rows are 44px tall for SC 2.5.5. The Switch's own track stays
          32x18.4 - that is the control's design - and the theme gives it a 44px
          `::before` overlay; the row is what an operator actually aims at, and the
          `<Label htmlFor>` already activates the Switch, so the whole row is one
          target. Two 44px rows at `gap-2` stack without overlapping. */}
      <SidebarFooter className="gap-2 p-3 pb-[calc(0.75rem_+_env(safe-area-inset-bottom))]">
        <div className="flex min-h-11 items-center justify-between">
          <Label htmlFor="debug-info" className="text-xs font-normal text-muted-foreground">
            Debug info
          </Label>
          <Switch id="debug-info" checked={debug} onCheckedChange={onDebugChange} />
        </div>
        <div className="flex min-h-11 items-center justify-between">
          <span className="text-xs text-muted-foreground">Appearance</span>
          <ThemeToggle />
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}

/**
 * The bottom messages panel: a VS Code-style log strip docked below the device
 * area, disclosed by its own title bar.
 *
 * The strip is a single-item accordion: the "Messages" bar is always visible
 * and clicking it expands or collapses the log beneath, chevron and height
 * animation included. The bar is sticky - the vector cards scroll in their own
 * region above it - and the log scrolls independently inside, following the
 * newest entry.
 *
 * While collapsed, a badge on the bar counts the messages received since the
 * log was last in view (from the client's total received, so the rolling
 * buffer's eviction cannot under-count) and clears as soon as the log opens.
 */
function MessagesPanel({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const client = useIndiClient();
  const [received, setReceived] = useState(0);
  const [seen, setSeen] = useState(0);
  useEffect(() => client.onMessage(() => setReceived((count) => count + 1)), [client]);
  useEffect(() => {
    if (open) setSeen(received);
  }, [open, received]);
  const unread = open ? 0 : received - seen;

  return (
    <aside
      aria-label="Messages"
      className="shrink-0 border-t bg-background pb-[env(safe-area-inset-bottom)]"
    >
      <Accordion
        type="single"
        collapsible
        value={open ? "messages" : ""}
        onValueChange={(value) => onOpenChange(value === "messages")}
      >
        <AccordionItem value="messages" className="border-b-0">
          {/* `min-h-14`, not `h-14`: at 200% text zoom (SC 1.4.4) the bar's label
              and its unread badge outgrow a fixed 56px and get clipped. */}
          <AccordionTrigger className="min-h-14 items-center rounded-none px-3 py-0">
            <span className="flex items-center gap-2">
              <MessageSquareText className="size-4 text-muted-foreground" />
              Messages
              {unread > 0 ? (
                <Badge className="h-5 min-w-5 rounded-full px-1 font-mono tabular-nums">
                  {unread > 99 ? "99+" : unread}
                </Badge>
              ) : null}
            </span>
          </AccordionTrigger>
          <AccordionContent className="p-0">
            {/* `h-auto max-h-56`, not `h-56`. A fixed height charged the strip
                224px whether it held two lines or two hundred, and the panel
                above it pays for that out of its own scroll area: at 1440x950
                the instrument grid was cut to 613px against 1089px of content,
                landing the cut on a group heading. "ALMANAC" then sat one pixel
                above this strip with its card below the fold, reading as a label
                for the log rather than for the instrument.

                `h-auto` overrides the `h-full` MessageLog carries for the case
                where a consumer gives it a sized box; the cap keeps a busy night
                from eating the panel, and the log scrolls inside it as before. */}
            <MessageLog className="h-auto max-h-56" limit={MESSAGE_LIMIT} />
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </aside>
  );
}

/** The main content: header + the selected device's property panel. */
function AppShell() {
  const devices = useDevices();
  const [selected, setSelected] = useState<string | null>(null);
  const [messagesOpen, setMessagesOpen] = useState(initialMessagesOpen);
  const [debug, setDebug] = useState(initialDebug);

  // Auto-select the first device (and recover if the selected one disappears).
  useEffect(() => {
    if ((selected === null || !devices.includes(selected)) && devices.length > 0) {
      setSelected(devices[0] ?? null);
    }
  }, [devices, selected]);

  const setMessagesOpenPersisted = useCallback((open: boolean) => {
    setMessagesOpen(open);
    try {
      localStorage.setItem(MESSAGES_KEY, open ? "open" : "closed");
    } catch {
      // Ignore storage errors (private mode, etc.).
    }
  }, []);

  const setDebugPersisted = useCallback((on: boolean) => {
    setDebug(on);
    try {
      localStorage.setItem(DEBUG_KEY, on ? "on" : "off");
    } catch {
      // Ignore storage errors (private mode, etc.).
    }
  }, []);

  const active = selected !== null && devices.includes(selected) ? selected : null;

  return (
    <DisplaySettingsProvider showDebug={debug}>
      {/* Page-level on purpose: a vector going into Alert on the device that is
          *not* on screen is the one an operator most needs to hear about, and a
          per-device announcer would only ever cover the selection. */}
      <StatusAnnouncer />
      <DeviceSidebar
        devices={devices}
        active={active}
        onSelect={setSelected}
        debug={debug}
        onDebugChange={setDebugPersisted}
      />
      {/* h-svh pins the shell to the viewport: the vector area scrolls in its
          own region and the messages strip below it stays visible. */}
      <SidebarInset className="h-svh">
        {/* The bar grows by the notch inset and pads by it, so the title keeps
            its 3.5rem of bar whether or not the browser reports one. `min-h`
            rather than `h`: at 200% text zoom the 44px sidebar trigger and the
            title outgrow 3.5rem, and a fixed height clips them. The underscores
            are Tailwind's spaces: `calc(3.5rem+env(…))` without whitespace around
            the `+` is invalid CSS and the whole declaration is dropped, which
            silently collapses the bar to its content. */}
        <header className="flex min-h-[calc(3.5rem_+_env(safe-area-inset-top))] shrink-0 items-center gap-3 border-b px-4 pt-[env(safe-area-inset-top)]">
          <Tooltip>
            <TooltipTrigger asChild>
              {/* SC 2.5.5 again: twMerge drops the primitive's own `size-7`. */}
              <SidebarTrigger className="size-11" />
            </TooltipTrigger>
            <TooltipContent>Toggle the device sidebar</TooltipContent>
          </Tooltip>
          <Separator orientation="vertical" className="h-5" />
          <h1 className="text-sm font-medium">{active ?? "INDIkit"}</h1>
        </header>
        <div className="min-h-0 min-w-0 flex-1 overflow-auto p-4">
          {active ? (
            <DevicePanel device={active} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Waiting for devices from indiserver…
            </div>
          )}
        </div>
        <MessagesPanel open={messagesOpen} onOpenChange={setMessagesOpenPersisted} />
      </SidebarInset>
    </DisplaySettingsProvider>
  );
}

/** Props for {@link App}. */
export interface AppProps {
  /**
   * An existing client to use (e.g. a simulated one for demos/tests); by
   * default the panel connects to the serving bridge's `/ws`.
   */
  client?: IndiClient;
}

/** The panel root: providers + shell. */
export default function App({ client }: AppProps) {
  return (
    <IndiProvider client={client}>
      <TooltipProvider delayDuration={150}>
        <SidebarProvider>
          <AppShell />
        </SidebarProvider>
        <Toaster />
      </TooltipProvider>
    </IndiProvider>
  );
}
