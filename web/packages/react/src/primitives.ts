/**
 * Re-exports of the themed shadcn/ui primitives.
 *
 * These are the standard shadcn components (Button, Card, Sidebar, ...) carrying
 * the INDINexus theme. They are re-exported so a consumer building their own
 * frontend gets both the INDI-aware components and the underlying primitives from
 * a single package.
 */

export { useIsMobile } from "@/hooks/use-mobile";
export { cn } from "@/lib/utils";
export * from "@/ui/accordion";
export * from "@/ui/badge";
export * from "@/ui/button";
export * from "@/ui/card";
export * from "@/ui/drawer";
export * from "@/ui/dropdown-menu";
export * from "@/ui/field";
export * from "@/ui/input";
export * from "@/ui/label";
export * from "@/ui/scroll-area";
export * from "@/ui/separator";
export * from "@/ui/sheet";
export * from "@/ui/sidebar";
export * from "@/ui/skeleton";
export * from "@/ui/sonner";
export * from "@/ui/switch";
export * from "@/ui/toggle";
export * from "@/ui/toggle-group";
export * from "@/ui/tooltip";
