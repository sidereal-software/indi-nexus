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
  TooltipProvider,
  useDevices,
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

/** The docked messages panel: the INDI log, always at hand like a status bar. */
function MessagesPanel() {
  return (
    <aside aria-label="Messages" className="flex w-80 shrink-0 flex-col border-l bg-background">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3 text-sm font-medium">
        <MessageSquareText className="size-4 text-muted-foreground" />
        Messages
      </div>
      <MessageLog className="min-h-0 flex-1" />
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

  const toggleMessages = useCallback(() => {
    setMessagesOpen((open) => {
      try {
        localStorage.setItem(MESSAGES_KEY, open ? "closed" : "open");
      } catch {
        // Ignore storage errors (private mode, etc.).
      }
      return !open;
    });
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
          <div className="ml-auto">
            <Button
              variant={messagesOpen ? "secondary" : "outline"}
              size="sm"
              aria-pressed={messagesOpen}
              onClick={toggleMessages}
            >
              <MessageSquareText data-icon="inline-start" />
              Messages
            </Button>
          </div>
        </header>
        <div className="flex min-h-0 flex-1">
          <main className="min-w-0 flex-1 overflow-auto p-4">
            {active ? (
              <DevicePanel device={active} />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Waiting for devices from indiserver…
              </div>
            )}
          </main>
          {messagesOpen ? <MessagesPanel /> : null}
        </div>
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
