import { useId, useState } from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

export function HelpTooltip({ content, className }: { content: string; className?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <span className={cn("relative inline-flex align-middle", className)}>
      <button
        type="button"
        className="inline-flex rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-describedby={open ? id : undefined}
        aria-label="More info"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((value) => !value)}
      >
        <Info className="h-3.5 w-3.5" />
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute left-0 top-full z-50 mt-1.5 w-56 rounded-md border border-border bg-card px-2.5 py-1.5 text-left text-xs font-normal leading-snug text-foreground shadow-md"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
        >
          {content}
        </span>
      )}
    </span>
  );
}
