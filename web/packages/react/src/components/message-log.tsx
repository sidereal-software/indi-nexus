/** A streaming, scrollable feed of INDI `message` notifications. */

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { Empty, EmptyTitle } from "@/ui/empty";
import { ScrollArea } from "@/ui/scroll-area";
import { useMessages } from "../hooks";

/** Render an ISO timestamp as a local time string, or empty when absent. */
function formatTime(timestamp: string | null | undefined): string {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString();
}

/** Props for {@link MessageLog}. */
export interface MessageLogProps {
  className?: string;
  /** Maximum messages to retain. */
  limit?: number;
}

/**
 * Show the most recent INDI messages, newest at the bottom.
 *
 * Follows the log: as entries stream in, the view keeps the newest message in
 * sight, so a permanently docked log behaves like a terminal tail.
 *
 * @param props - Optional class name and retention limit.
 * @returns The message log element.
 */
export function MessageLog({ className, limit = 200 }: MessageLogProps) {
  const messages = useMessages(limit);
  const endRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (messages.length === 0) return;
    const end = endRef.current;
    // Guarded: jsdom (tests) has no scrollIntoView.
    if (end && typeof end.scrollIntoView === "function") end.scrollIntoView({ block: "end" });
  }, [messages]);
  return (
    <ScrollArea className={cn("h-full", className)}>
      <div className="flex flex-col gap-2.5 p-3 font-mono text-xs">
        {messages.length === 0 ? (
          // Minimal on purpose: this is a docked strip, so the full Empty block with
          // media and a description would dwarf the log it stands in for.
          <Empty className="border-none p-0 text-left">
            <EmptyTitle className="font-normal text-muted-foreground text-xs">
              No messages yet.
            </EmptyTitle>
          </Empty>
        ) : (
          messages.map((message, index) => (
            // Each entry stacks a time/device header over the (possibly long)
            // message text, so wrapped lines start at the margin, not mid-row.
            // biome-ignore lint/suspicious/noArrayIndexKey: log lines have no stable id
            <div key={index} className="flex flex-col gap-0.5">
              <div className="flex items-baseline gap-2">
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  {formatTime(message.timestamp)}
                </span>
                {message.device ? (
                  <span className="truncate text-primary">{message.device}</span>
                ) : null}
              </div>
              <span className="whitespace-pre-wrap break-words">{message.message}</span>
            </div>
          ))
        )}
        <div ref={endRef} aria-hidden />
      </div>
    </ScrollArea>
  );
}
