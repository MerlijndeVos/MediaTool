import { useEffect, useId, useRef, useState } from "react";
import { AlertTriangle, ChevronDown, Eye, FolderOpen, Loader2, Play } from "lucide-react";
import { isDesktopApp, pickFolder } from "@/lib/desktop";
import { Button } from "@/components/ui/button";
import { HelpTooltip } from "@/components/ui/help-tooltip";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

function FieldLabel({ label, tooltip }: { label: string; tooltip?: string }) {
  return (
    <Label className="inline-flex items-center gap-1.5">
      {label}
      {tooltip && <HelpTooltip content={tooltip} />}
    </Label>
  );
}

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
      className="app-dialog z-50"
      onClose={() => onOpenChange(false)}
      onClick={(e) => {
        if (e.target === dialogRef.current) onOpenChange(false);
      }}
    >
      <div className="space-y-4 p-6" onClick={(e) => e.stopPropagation()}>
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
  tooltip,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
  tooltip?: string;
}) {
  return (
    <div className="space-y-1.5">
      <FieldLabel label={label} tooltip={tooltip} />
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
  tooltip,
  browse = "folder",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  hint?: string;
  tooltip?: string;
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
    <Field label={label} hint={hint} tooltip={tooltip}>
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
  tooltip,
  disabled = false,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  hint?: string;
  tooltip?: string;
  disabled?: boolean;
}) {
  const switchId = useId();
  const Wrapper = disabled ? "div" : "label";
  const wrapperProps = disabled ? {} : { htmlFor: switchId };

  return (
    <Wrapper
      {...wrapperProps}
      className={cn(
        "flex items-center gap-2.5 rounded-md border px-2.5 py-2 transition-colors",
        disabled ? "cursor-default" : "cursor-pointer",
        checked
          ? "border-primary/50 bg-primary/10 shadow-sm"
          : "border-border/60 bg-muted/30",
      )}
    >
      <Switch
        id={switchId}
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
        className="shrink-0"
      />
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-sm",
            checked && "text-foreground",
          )}
        >
          <span className="font-medium">{label}</span>
          {hint && <span className="text-xs font-normal text-muted-foreground">{hint}</span>}
          {tooltip && (
            <span
              className="inline-flex shrink-0"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => e.stopPropagation()}
            >
              <HelpTooltip content={tooltip} />
            </span>
          )}
        </p>
      </div>
    </Wrapper>
  );
}

export function SelectField({
  label,
  value,
  onChange,
  options,
  tooltip,
  hint,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  tooltip?: string;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <Field label={label} hint={hint} tooltip={tooltip}>
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className="flex h-10 w-full appearance-none rounded-md border border-input bg-background pl-3 pr-8 text-left text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <ChevronDown
          className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
      </div>
    </Field>
  );
}

export function LanguageCombobox({
  label,
  value,
  onChange,
  languages,
  includeAuto = false,
  hint,
  tooltip,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  languages: { code: string; label: string }[];
  includeAuto?: boolean;
  hint?: string;
  tooltip?: string;
}) {
  const options = [
    ...(includeAuto ? [{ value: "auto", label: "Auto (from filename)" }] : []),
    ...languages.map((lang) => ({
      value: lang.code,
      label: `${lang.label} (${lang.code})`,
    })),
  ];

  const selectValue = options.some((o) => o.value === value)
    ? value
    : includeAuto
      ? "auto"
      : (options[0]?.value ?? value);

  return (
    <SelectField
      label={label}
      value={selectValue}
      onChange={onChange}
      options={options}
      hint={hint}
      tooltip={tooltip}
    />
  );
}
