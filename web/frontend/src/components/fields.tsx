import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Eye, FolderOpen, Loader2, Play } from "lucide-react";
import { isDesktopApp, pickFolder } from "@/lib/desktop";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

function ApplyConfirmDialog({
  open,
  onOpenChange,
  onConfirm,
  hint,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  hint?: string;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    else if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-background p-0 shadow-lg backdrop:bg-black/50 open:animate-in"
      onClose={() => onOpenChange(false)}
      onClick={(e) => {
        if (e.target === dialogRef.current) onOpenChange(false);
      }}
    >
      <div className="space-y-4 p-6">
        <div className="flex gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-500/15 text-red-700 dark:text-red-300">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="space-y-1">
            <h2 className="text-lg font-semibold text-foreground">Apply changes?</h2>
            <p className="text-sm text-muted-foreground">
              This runs for real. Files and folders may be created, moved, renamed, edited, or deleted.
            </p>
            {hint && <p className="text-sm text-muted-foreground">{hint}</p>}
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={() => {
              onOpenChange(false);
              onConfirm();
            }}
          >
            Apply changes
          </Button>
        </div>
      </div>
    </dialog>
  );
}

export function ToolRunActions({
  onPreview,
  onApply,
  disabled,
  loading,
  applyHint,
}: {
  onPreview: () => void;
  onApply: () => void;
  disabled?: boolean;
  loading?: boolean;
  applyHint?: string;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);

  return (
    <div className="space-y-3 border-t border-border/60 pt-4">
      <p className="text-xs text-muted-foreground">
        Preview logs planned actions without writing to disk. Apply makes permanent changes.
      </p>
      <div className="flex flex-wrap gap-3">
        <Button
          type="button"
          onClick={onPreview}
          disabled={disabled}
          variant="secondary"
          size="lg"
          className={cn(
            "border-amber-500/50 bg-amber-500/15 text-amber-950 hover:bg-amber-500/25 dark:text-amber-50",
          )}
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
          Preview
        </Button>
        <Button
          type="button"
          onClick={() => setConfirmOpen(true)}
          disabled={disabled}
          variant="default"
          size="lg"
          className="shadow-sm"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Apply
        </Button>
      </div>
      <ApplyConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        onConfirm={onApply}
        hint={applyHint}
      />
    </div>
  );
}

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
