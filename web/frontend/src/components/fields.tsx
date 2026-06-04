import { useState } from "react";
import { AlertTriangle, Eye, FolderOpen } from "lucide-react";
import { isDesktopApp, pickFolder } from "@/lib/desktop";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

/** Safe default: preview planned actions before writing to disk. */
export const DEFAULT_DRY_RUN = true;

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function PathField({
  label,
  value,
  onChange,
  placeholder = "C:\\path\\to\\folder",
  hint,
  browse = "folder",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  hint?: string;
  /** Show a native Browse button in the desktop app (`folder` only for now). */
  browse?: "folder" | false;
}) {
  const [picking, setPicking] = useState(false);
  const showBrowse = browse === "folder" && isDesktopApp();

  const handleBrowse = async () => {
    setPicking(true);
    try {
      const path = await pickFolder();
      if (path) onChange(path);
    } finally {
      setPicking(false);
    }
  };

  return (
    <Field label={label} hint={hint}>
      <div className="flex gap-2">
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="min-w-0 flex-1"
        />
        {showBrowse && (
          <Button
            type="button"
            variant="outline"
            onClick={handleBrowse}
            disabled={picking}
            className="shrink-0"
          >
            <FolderOpen className="h-4 w-4" />
            Browse
          </Button>
        )}
      </div>
    </Field>
  );
}

export function CheckField({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  hint?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-border/60 bg-muted/30 px-3 py-2.5">
      <div>
        <p className="text-sm font-medium">{label}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
}

export function DryRunField({
  dryRun,
  onChange,
  hint,
}: {
  dryRun: boolean;
  onChange: (v: boolean) => void;
  hint?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border-2 px-4 py-3 transition-colors",
        dryRun
          ? "border-amber-500/70 bg-amber-500/10 dark:border-amber-400/50 dark:bg-amber-500/15"
          : "border-red-500/60 bg-red-500/5 dark:border-red-400/50 dark:bg-red-500/10",
      )}
      role="group"
      aria-label={dryRun ? "Dry run enabled" : "Apply changes enabled"}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-3">
          <div
            className={cn(
              "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
              dryRun ? "bg-amber-500/20 text-amber-700 dark:text-amber-300" : "bg-red-500/15 text-red-700 dark:text-red-300",
            )}
          >
            {dryRun ? <Eye className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
          </div>
          <div>
            <p className={cn("text-sm font-semibold", dryRun ? "text-amber-900 dark:text-amber-100" : "text-red-900 dark:text-red-100")}>
              {dryRun ? "Dry run — preview only" : "Apply changes — writes to disk"}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {dryRun
                ? "Shows planned actions in the log without creating, moving, or editing files."
                : "Runs for real. Files and folders may be created, moved, renamed, or deleted."}
            </p>
            {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <Switch checked={dryRun} onCheckedChange={onChange} aria-label="Dry run" />
          <span className={cn("text-[10px] font-semibold uppercase tracking-wide", dryRun ? "text-amber-700 dark:text-amber-400" : "text-red-700 dark:text-red-400")}>
            {dryRun ? "On" : "Off"}
          </span>
        </div>
      </div>
    </div>
  );
}

export function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <Field label={label}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  );
}
