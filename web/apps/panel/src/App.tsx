/**
 * The reference INDINexus panel.
 *
 * Everything here is composed from `@indi-nexus/react`: the `IndiProvider` (which
 * connects to the bridge at `/ws`), the hooks, the INDI-aware components, and the
 * themed shadcn primitives. It doubles as a worked example of "build your own UI
 * on the library".
 */

import {
  Button,
  ConnectionStatus,
  cn,
  DevicePanel,
  DisplaySettingsProvider,
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
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
  Toggle,
  TooltipProvider,
  useDevices,
  useIsMobile,
} from "@indi-nexus/react";
import { MessageSquareText, Moon, Radio, Sun, Telescope } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTheme } from "./use-theme";

/** localStorage key remembering whether the messages panel is open. */
const MESSAGES_KEY = "indi-messages";

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
    <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
      {theme === "dark" ? <Sun /> : <Moon />}
    </Button>
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
      <SidebarHeader className="gap-3 p-3">
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
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="gap-2 p-3">
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
 * The desktop right rail: the INDI message log, a mirror of the device sidebar.
 *
 * Stays mounted and animates its width with the same duration/easing as the
 * device sidebar, so opening feels identical; while closed it is hidden from
 * the accessibility tree and inert.
 */
function MessagesSidebar({ open }: { open: boolean }) {
  return (
    <div
      aria-hidden={!open}
      inert={!open}
      className={cn(
        "shrink-0 overflow-hidden transition-[width] duration-200 ease-linear",
        open ? "w-(--sidebar-width)" : "w-0",
      )}
    >
      <Sidebar
        side="right"
        collapsible="none"
        role="complementary"
        aria-label="Messages"
        className="h-svh w-(--sidebar-width) border-l"
      >
        <SidebarHeader className="p-3">
          <div className="flex items-center gap-2">
            <MessageSquareText className="size-5 text-primary" />
            <span className="text-sm font-semibold">Messages</span>
          </div>
        </SidebarHeader>
        <SidebarContent className="overflow-hidden">
          <MessageLog className="min-h-0 flex-1" />
        </SidebarContent>
      </Sidebar>
    </div>
  );
}

/** The mobile presentation: the same log in a swipe-dismissable bottom drawer. */
function MessagesDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle className="flex items-center justify-center gap-2">
            <MessageSquareText className="size-5 text-primary" />
            Messages
          </DrawerTitle>
        </DrawerHeader>
        <MessageLog className="h-[50svh]" />
      </DrawerContent>
    </Drawer>
  );
}

/** The main content: header + the selected device's property panel. */
function AppShell() {
  const devices = useDevices();
  const isMobile = useIsMobile();
  const [selected, setSelected] = useState<string | null>(null);
  const [messagesOpen, setMessagesOpen] = useState(initialMessagesOpen);
  // The mobile drawer is transient and never persisted: it must not cover the
  // controls on load just because the desktop rail was left open.
  const [drawerOpen, setDrawerOpen] = useState(false);
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
      <DeviceSidebar
        devices={devices}
        active={active}
        onSelect={setSelected}
        debug={debug}
        onDebugChange={setDebugPersisted}
      />
      <SidebarInset>
        <header className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-5" />
          <h1 className="text-sm font-medium">{active ?? "INDINexus"}</h1>
          <Toggle
            size="sm"
            className="ml-auto size-7 min-w-7 p-0"
            pressed={isMobile ? drawerOpen : messagesOpen}
            onPressedChange={(pressed) =>
              isMobile ? setDrawerOpen(pressed) : setMessagesOpenPersisted(pressed)
            }
            aria-label="Toggle messages"
          >
            <MessageSquareText />
          </Toggle>
        </header>
        <main className="min-h-0 min-w-0 flex-1 overflow-auto p-4">
          {active ? (
            <DevicePanel device={active} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Waiting for devices from indiserver…
            </div>
          )}
        </main>
      </SidebarInset>
      {isMobile ? (
        <MessagesDrawer open={drawerOpen} onOpenChange={setDrawerOpen} />
      ) : (
        <MessagesSidebar open={messagesOpen} />
      )}
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
