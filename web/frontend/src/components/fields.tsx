import { useState } from "react";
import { FolderOpen } from "lucide-react";
import { isDesktopApp, pickFolder } from "@/lib/desktop";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

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
