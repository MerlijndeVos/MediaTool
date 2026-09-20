import { useMemo, useState } from "react";
import { Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CheckField, Field, PathField, SelectField, ToolRunActions } from "@/components/fields";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { ModInfo, ModParam } from "@/lib/types";

type FormValue = string | boolean;
type FormValues = Record<string, FormValue>;

/** What the field shows first: the manifest's `initial`, else its `default`. */
function initialValue(param: ModParam): FormValue {
  const raw = param.initial !== undefined ? param.initial : param.default;
  switch (param.type) {
    case "bool":
      return Boolean(raw);
    case "files":
    case "list":
      return Array.isArray(raw) ? raw.join("\n") : "";
    case "json":
      return raw && typeof raw === "object" ? JSON.stringify(raw, null, 2) : "";
    case "choice":
      return raw == null ? (param.choices[0]?.value ?? "") : String(raw);
    default:
      return raw == null ? "" : String(raw);
  }
}

function isEmpty(value: FormValue | undefined): boolean {
  return typeof value === "string" ? value.trim() === "" : false;
}

/** Convert what the user typed into the JSON value the API expects; `undefined` = leave out. */
function toPayloadValue(param: ModParam, value: FormValue): unknown {
  if (param.type === "bool") return value;
  const text = String(value);
  switch (param.type) {
    case "integer":
    case "number": {
      if (text.trim() === "") return param.nullable ? null : undefined;
      const n = Number(text);
      if (Number.isNaN(n)) throw new Error(`${param.label} must be a number.`);
      return n;
    }
    case "files":
    case "list":
      return text
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
    case "json": {
      if (text.trim() === "") return param.nullable ? null : undefined;
      try {
        return JSON.parse(text);
      } catch {
        throw new Error(`${param.label} is not valid JSON.`);
      }
    }
    default:
      return param.nullable && text.trim() === "" ? null : text;
  }
}

const TEXTAREA_CLASS =
  "flex min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

function ParamField({
  param,
  value,
  onChange,
}: {
  param: ModParam;
  value: FormValue;
  onChange: (value: FormValue) => void;
}) {
  const tooltip = param.help || undefined;
  const placeholder = param.placeholder || undefined;

  switch (param.type) {
    case "bool":
      return (
        <CheckField
          label={param.label}
          checked={Boolean(value)}
          onChange={onChange}
          tooltip={tooltip}
        />
      );
    case "choice":
      return (
        <SelectField
          label={param.label}
          value={String(value)}
          onChange={onChange}
          tooltip={tooltip}
          options={param.choices}
        />
      );
    case "folder":
    case "file":
      return (
        <PathField
          label={param.label}
          value={String(value)}
          onChange={onChange}
          placeholder={placeholder}
          tooltip={tooltip}
          browse={param.type}
        />
      );
    case "integer":
    case "number":
      return (
        <Field label={param.label} tooltip={tooltip}>
          <Input
            type="number"
            value={String(value)}
            min={param.min ?? undefined}
            max={param.max ?? undefined}
            step={param.type === "integer" ? 1 : "any"}
            placeholder={placeholder}
            onChange={(e) => onChange(e.target.value)}
          />
        </Field>
      );
    case "files":
    case "list":
    case "json":
      return (
        <Field
          label={param.label}
          tooltip={tooltip}
          hint={param.type === "json" ? "JSON" : "One entry per line."}
        >
          <textarea
            className={cn(TEXTAREA_CLASS, param.type === "json" && "font-mono")}
            value={String(value)}
            placeholder={placeholder}
            onChange={(e) => onChange(e.target.value)}
          />
        </Field>
      );
    default:
      return (
        <Field label={param.label} tooltip={tooltip}>
          <Input
            value={String(value)}
            placeholder={placeholder}
            onChange={(e) => onChange(e.target.value)}
          />
        </Field>
      );
  }
}

/**
 * A tool form generated from a mod's `[[params]]` manifest tables, so a mod needs no
 * frontend code. Preview / Apply buttons drive the manifest's `mode_param`.
 */
export function ModForm({
  mod,
  onRun,
  disabled,
}: {
  mod: ModInfo;
  onRun: (params: Record<string, unknown>) => void;
  disabled?: boolean;
}) {
  const params = useMemo(() => mod.params.filter((p) => p.ui), [mod]);
  const [values, setValues] = useState<FormValues>(() =>
    Object.fromEntries(params.map((p) => [p.name, initialValue(p)])),
  );
  const [formError, setFormError] = useState<string | null>(null);

  const missingRequired = params.some(
    (p) => p.required && p.type !== "bool" && isEmpty(values[p.name]),
  );

  const submit = (preview: boolean) => {
    const payload: Record<string, unknown> = {};
    try {
      for (const p of params) {
        const v = toPayloadValue(p, values[p.name]);
        if (v !== undefined) payload[p.name] = v;
      }
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
      return;
    }
    setFormError(null);
    if (mod.ui.run_mode === "preview_apply") {
      // `dry_run` is true for a preview; an `apply` param (mode_inverted) is the opposite.
      payload[mod.ui.mode_param] = preview !== mod.ui.mode_inverted;
    }
    onRun(payload);
  };

  const blocked = disabled || missingRequired;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {params.map((p) => (
          <div key={p.name} className={p.width === "half" ? undefined : "sm:col-span-2"}>
            <ParamField
              param={p}
              value={values[p.name]}
              onChange={(v) => setValues((prev) => ({ ...prev, [p.name]: v }))}
            />
          </div>
        ))}
      </div>
      {formError && <p className="text-sm text-red-600 dark:text-red-400">{formError}</p>}
      {mod.ui.run_mode === "preview_apply" ? (
        <ToolRunActions
          loading={disabled}
          disabled={blocked}
          applyHint={mod.ui.apply_hint || undefined}
          onPreview={() => submit(true)}
          onApply={() => submit(false)}
        />
      ) : (
        <div className="border-t border-border/60 pt-4">
          <Button type="button" size="lg" disabled={blocked} onClick={() => submit(false)}>
            {disabled ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Run
          </Button>
        </div>
      )}
    </div>
  );
}
