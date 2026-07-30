/** A streaming, scrollable feed of INDI `message` notifications. */

import { cn } from "@/lib/utils";
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
 * @param props - Optional class name and retention limit.
 * @returns The message log element.
 */
export function MessageLog({ className, limit = 200 }: MessageLogProps) {
  const messages = useMessages(limit);
  return (
    <ScrollArea className={cn("h-full", className)}>
      <div className="flex flex-col gap-1 p-3 font-mono text-xs">
        {messages.length === 0 ? (
          <p className="text-muted-foreground">No messages yet.</p>
        ) : (
          messages.map((message, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: log lines have no stable id
            <div key={index} className="flex gap-2">
              <span className="shrink-0 tabular-nums text-muted-foreground">
                {formatTime(message.timestamp)}
              </span>
              {message.device ? (
                <span className="shrink-0 text-primary">{message.device}</span>
              ) : null}
              <span className="whitespace-pre-wrap break-words">{message.message}</span>
            </div>
          ))
        )}
      </div>
    </ScrollArea>
  );
}
