import { ChevronDown, ChevronUp, Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { LogLine } from "@/lib/types";

interface LogDrawerProps {
  open: boolean;
  onToggle: () => void;
  logs: LogLine[];
  onClear: () => void;
}

export function LogDrawer({ open, onToggle, logs, onClear }: LogDrawerProps) {
  return (
    <div
      className={cn(
        "fixed bottom-0 left-0 right-0 z-40 border-t bg-card shadow-lg transition-all",
        open ? "h-64" : "h-11",
      )}
    >
      <div className="flex h-11 items-center justify-between border-b px-4">
        <button
          type="button"
          onClick={onToggle}
          className="flex items-center gap-2 text-sm font-medium hover:text-primary"
        >
          <Terminal className="h-4 w-4" />
          Log
          <span className="text-muted-foreground">({logs.length})</span>
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
        </button>
        <Button variant="ghost" size="sm" onClick={onClear}>
          Clear
        </Button>
      </div>
      {open && (
        <pre className="h-[calc(100%-2.75rem)] overflow-auto p-4 font-mono text-xs leading-relaxed text-muted-foreground">
          {logs.length === 0 ? (
            <span className="text-muted-foreground/70">Output from jobs will appear here…</span>
          ) : (
            logs.map((line, i) => (
              <div
                key={`${line.ts}-${i}`}
                className={cn(
                  line.level >= 40 && "text-red-500 dark:text-red-400",
                  line.level === 30 && "text-amber-600 dark:text-amber-400",
                )}
              >
                {line.message}
              </div>
            ))
          )}
        </pre>
      )}
    </div>
  );
}
