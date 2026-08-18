/**
 * The reference INDINexus panel.
 *
 * Everything here is composed from `@indi-nexus/react`: the `IndiProvider` (which
 * connects to the bridge at `/ws`), the hooks, the INDI-aware components, and the
 * themed shadcn primitives. It doubles as a worked example of "build your own UI
 * on the library".
 */

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
  AlertAnnouncer,
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
  Switch,
  Toaster,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
  useDevices,
  useIndiClient,
} from "@indi-nexus/react";
import { MessageSquareText, Moon, Radio, Sun, Telescope } from "lucide-react";
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

/** An icon button toggling light/dark. */
function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
          {theme === "dark" ? <Sun /> : <Moon />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        {theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      </TooltipContent>
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
  return (
    <Sidebar>
      <SidebarHeader className="gap-3 p-3 pt-[calc(0.75rem_+_env(safe-area-inset-top))]">
        <div className="flex items-center gap-2">
          <Telescope className="size-5 text-primary" />
          <span className="text-sm font-semibold">
            INDI<span className="text-primary">Nexus</span>
          </span>
        </div>
        <ConnectionStatus />
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Devices</SidebarGroupLabel>
          <SidebarGroupContent>
            {/* The sidebar's own markup is all `div`s, so without this the device
                list - the page's only means of moving between devices - sits
                outside every landmark and a landmark walk finds only the main
                region and the messages strip. */}
            <nav aria-label="Devices">
              <SidebarMenu>
                {devices.length === 0 ? (
                  <p className="px-2 py-1.5 text-xs text-muted-foreground">No devices connected.</p>
                ) : (
                  devices.map((device) => (
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
                  ))
                )}
                {/* Configuration acts on the selected device, so it sits at the
                    end of the same menu the selection lives in. It renders
                    nothing when nothing is selected or the device has no
                    CONFIG_PROCESS. */}
                <DeviceConfigDialog device={active} />
              </SidebarMenu>
            </nav>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="gap-2 p-3 pb-[calc(0.75rem_+_env(safe-area-inset-bottom))]">
        <div className="flex items-center justify-between">
          <Label htmlFor="debug-info" className="text-xs font-normal text-muted-foreground">
            Debug info
          </Label>
          <Switch id="debug-info" checked={debug} onCheckedChange={onDebugChange} />
        </div>
        <div className="flex items-center justify-between">
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
          <AccordionTrigger className="h-14 items-center rounded-none px-3 py-0">
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
            <MessageLog className="h-56" limit={MESSAGE_LIMIT} />
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
      <AlertAnnouncer />
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
            its 3.5rem of bar whether or not the browser reports one. The
            underscores are Tailwind's spaces: `calc(3.5rem+env(…))` without
            whitespace around the `+` is invalid CSS and the whole declaration
            is dropped, which silently collapses the bar to its content. */}
        <header className="flex h-[calc(3.5rem_+_env(safe-area-inset-top))] shrink-0 items-center gap-3 border-b px-4 pt-[env(safe-area-inset-top)]">
          <Tooltip>
            <TooltipTrigger asChild>
              <SidebarTrigger />
            </TooltipTrigger>
            <TooltipContent>Toggle the device sidebar</TooltipContent>
          </Tooltip>
          <Separator orientation="vertical" className="h-5" />
          <h1 className="text-sm font-medium">{active ?? "INDINexus"}</h1>
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
