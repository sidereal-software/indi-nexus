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
  IndiProvider,
  MessageLog,
  Separator,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
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
  Toaster,
  TooltipProvider,
  useDevices,
} from "@indi-nexus/react";
import { MessageSquareText, Moon, Radio, Sun, Telescope } from "lucide-react";
import { useEffect, useState } from "react";
import { useTheme } from "./use-theme";

/** An icon button toggling light/dark. */
function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
      {theme === "dark" ? <Sun /> : <Moon />}
    </Button>
  );
}

/** The left sidebar: brand, connection state, device list, theme toggle. */
function DeviceSidebar({
  devices,
  active,
  onSelect,
}: {
  devices: readonly string[];
  active: string | null;
  onSelect: (device: string) => void;
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
      <SidebarFooter className="p-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Appearance</span>
          <ThemeToggle />
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}

/** The main content: header + the selected device's property panel. */
function AppShell() {
  const devices = useDevices();
  const [selected, setSelected] = useState<string | null>(null);

  // Auto-select the first device (and recover if the selected one disappears).
  useEffect(() => {
    if ((selected === null || !devices.includes(selected)) && devices.length > 0) {
      setSelected(devices[0] ?? null);
    }
  }, [devices, selected]);

  const active = selected !== null && devices.includes(selected) ? selected : null;

  return (
    <>
      <DeviceSidebar devices={devices} active={active} onSelect={setSelected} />
      <SidebarInset>
        <header className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-5" />
          <h1 className="text-sm font-medium">{active ?? "INDINexus"}</h1>
          <div className="ml-auto">
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" size="sm">
                  <MessageSquareText data-icon="inline-start" />
                  Messages
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-md">
                <SheetHeader className="border-b">
                  <SheetTitle>Messages</SheetTitle>
                </SheetHeader>
                <MessageLog className="min-h-0 flex-1" />
              </SheetContent>
            </Sheet>
          </div>
        </header>
        <main className="flex-1 overflow-auto p-4">
          {active ? (
            <DevicePanel device={active} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Waiting for devices from indiserver…
            </div>
          )}
        </main>
      </SidebarInset>
    </>
  );
}

/** The panel root: providers + shell. */
export default function App() {
  return (
    <IndiProvider>
      <TooltipProvider delayDuration={150}>
        <SidebarProvider>
          <AppShell />
        </SidebarProvider>
        <Toaster />
      </TooltipProvider>
    </IndiProvider>
  );
}
