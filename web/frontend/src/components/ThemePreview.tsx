import { previewStyle } from "@/lib/theme";
import type { ThemeData } from "@/lib/types";
import { cn } from "@/lib/utils";

/** The colours a theme is judged by, as a strip. */
export function Swatches({ colors, className }: { colors: string[]; className?: string }) {
  return (
    <span className={cn("flex overflow-hidden rounded-md border border-border", className)} aria-hidden>
      {colors.map((color, i) => (
        <span key={`${color}-${i}`} className="h-5 flex-1" style={{ backgroundColor: color }} />
      ))}
    </span>
  );
}

/**
 * A small mock screen drawn with a theme's own colours, whatever theme the app itself is using:
 * the variables are set on this box only.
 */
export function ThemePreview({ theme, mode }: { theme: ThemeData; mode: "light" | "dark" }) {
  return (
    <div
      style={previewStyle(theme, mode)}
      className="space-y-2 rounded-lg border border-border bg-background p-3 font-sans text-foreground"
    >
      <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {mode === "light" ? "Light" : "Dark"}
      </p>
      <div className="flex items-center gap-2 rounded-lg bg-category-media/15 px-2 py-1.5">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-category-media text-[10px] text-category-foreground">
          M
        </span>
        <span className="truncate text-xs font-semibold">Convert</span>
      </div>
      <div className="rounded-md border border-border bg-card p-2 text-card-foreground">
        <p className="text-xs font-medium">A panel</p>
        <p className="text-[11px] text-muted-foreground">Quiet text looks like this.</p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <span className="rounded-md bg-primary px-2 py-0.5 text-[11px] font-medium text-primary-foreground">
            Run
          </span>
          <span className="rounded-md bg-destructive px-2 py-0.5 text-[11px] font-medium text-destructive-foreground">
            Remove
          </span>
          <span className="rounded-md border border-danger/40 bg-danger/10 px-2 py-0.5 text-[11px] text-danger-text">
            Error
          </span>
          <span className="rounded-md border border-success/40 bg-success/10 px-2 py-0.5 text-[11px] text-success-text">
            Done
          </span>
        </div>
      </div>
    </div>
  );
}
