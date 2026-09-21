import { useMemo, useState } from "react";
import { Loader2, Play, Zap } from "lucide-react";
import { runModAction } from "@/api/client";
import { Button } from "@/components/ui/button";
import { CheckField, Field, PathField, SelectField, ToolRunActions } from "@/components/fields";
import { MarkdownLite } from "@/components/MarkdownLite";
import { ModResults } from "@/components/ModResults";
import { Input } from "@/components/ui/input";
import { type FormValue, type FormValues, isShown } from "@/lib/showIf";
import { cn } from "@/lib/utils";
import type { ModAction, ModInfo, ModParam, ModResult } from "@/lib/types";

/** What the field shows first: the manifest's `initial`, else its `default`. */
function initialValue(param: ModParam): FormValue {
  const raw = param.initial !== undefined ? param.initial : param.default;
  switch (param.type) {
    case "bool":
      return Boolean(raw);
    case "files":
    case "list":
      return Array.isArray(raw) ? raw.join("\n") : "";
    case "multichoice":
      return Array.isArray(raw) ? raw.map(String) : [];
    case "json":
      return raw && typeof raw === "object" ? JSON.stringify(raw, null, 2) : "";
    case "choice":
      return raw == null ? (param.choices[0]?.value ?? "") : String(raw);
    case "integer":
    case "number":
      // A slider always has a position, so it starts at its minimum when there is no default.
      if (raw == null && param.widget === "slider") return String(param.min ?? 0);
      return raw == null ? "" : String(raw);
    default:
      return raw == null ? "" : String(raw);
  }
}

function isEmpty(value: FormValue | undefined): boolean {
  if (Array.isArray(value)) return value.length === 0;
  return typeof value === "string" ? value.trim() === "" : false;
}

/** Convert what the user typed into the JSON value the API expects; `undefined` = leave out. */
function toPayloadValue(param: ModParam, value: FormValue): unknown {
  if (param.type === "bool") return value;
  if (param.type === "multichoice") return Array.isArray(value) ? value : [];
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

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

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
    case "multichoice": {
      const ticked = Array.isArray(value) ? value : [];
      const toggle = (choice: string) =>
        onChange(ticked.includes(choice) ? ticked.filter((c) => c !== choice) : [...ticked, choice]);
      return (
        <Field label={param.label} tooltip={tooltip}>
          <div className="flex flex-wrap gap-x-4 gap-y-2" role="group" aria-label={param.label}>
            {param.choices.map((choice) => (
              <label key={choice.value} className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={ticked.includes(choice.value)}
                  onChange={() => toggle(choice.value)}
                />
                {choice.label}
              </label>
            ))}
          </div>
        </Field>
      );
    }
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
      if (param.widget === "slider") {
        return (
          <Field label={`${param.label}: ${String(value)}`} tooltip={tooltip}>
            <input
              type="range"
              className="w-full accent-primary"
              value={String(value)}
              min={param.min ?? 0}
              max={param.max ?? 100}
              step={param.step ?? (param.type === "integer" ? 1 : "any")}
              onChange={(e) => onChange(e.target.value)}
              aria-label={param.label}
            />
          </Field>
        );
      }
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
    case "color":
      return (
        <Field label={param.label} tooltip={tooltip}>
          <div className="flex gap-2">
            <input
              type="color"
              className="h-10 w-14 shrink-0 cursor-pointer rounded-md border border-input bg-background p-1"
              value={HEX_RE.test(String(value)) ? String(value) : "#000000"}
              onChange={(e) => onChange(e.target.value)}
              aria-label={`${param.label}: pick a colour`}
            />
            <Input
              value={String(value)}
              placeholder={placeholder ?? "#rrggbb"}
              onChange={(e) => onChange(e.target.value)}
              className="min-w-0 flex-1 font-mono"
            />
          </div>
        </Field>
      );
    case "date":
      return (
        <Field label={param.label} tooltip={tooltip}>
          <Input type="date" value={String(value)} onChange={(e) => onChange(e.target.value)} />
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

function ParamGrid({
  params,
  values,
  onChange,
}: {
  params: ModParam[];
  values: FormValues;
  onChange: (name: string, value: FormValue) => void;
}) {
  if (params.length === 0) return null;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {params.map((p) => (
        <div key={p.name} className={p.width === "half" ? undefined : "sm:col-span-2"}>
          <ParamField param={p} value={values[p.name]} onChange={(v) => onChange(p.name, v)} />
        </div>
      ))}
    </div>
  );
}

/**
 * A tool form generated from a mod's manifest, so a mod needs no frontend code (and none of its
 * code runs in the page): `[[params]]` become fields, `[[sections]]` group them (as blocks or
 * tabs), `show_if` hides what does not matter yet, and `[[actions]]` add extra buttons.
 * Preview / Apply buttons drive the manifest's `mode_param`.
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
  const [tab, setTab] = useState<string | null>(null);
  const [actionResults, setActionResults] = useState<ModResult[]>([]);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  const setValue = (name: string, value: FormValue) => setValues((prev) => ({ ...prev, [name]: value }));

  // What is on screen right now: a field is shown when its own and its section's show_if hold.
  const sectionShown = useMemo(
    () => new Map(mod.sections.map((s) => [s.id, isShown(s.show_if, values)])),
    [mod.sections, values],
  );
  const shown = (p: ModParam) =>
    isShown(p.show_if, values) && (!p.section || sectionShown.get(p.section) !== false);
  const visible = params.filter(shown);

  const missingRequired = visible.some((p) => p.required && p.type !== "bool" && isEmpty(values[p.name]));

  const submit = (preview: boolean) => {
    const payload: Record<string, unknown> = {};
    try {
      // A hidden field sends nothing, so the mod gets its default.
      for (const p of visible) {
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

  const actionParams = (action: ModAction) => {
    const wanted = action.params ?? params.map((p) => p.name);
    return params.filter((p) => wanted.includes(p.name));
  };

  const runAction = async (action: ModAction) => {
    const payload: Record<string, unknown> = {};
    try {
      for (const p of actionParams(action)) {
        const v = toPayloadValue(p, values[p.name]);
        if (v !== undefined) payload[p.name] = v;
      }
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
      return;
    }
    setFormError(null);
    setActionBusy(action.name);
    try {
      setActionResults((await runModAction(mod.id, action.name, payload)).results);
    } catch (e) {
      setActionResults([
        { view: "message", title: "", level: "error", text: e instanceof Error ? e.message : String(e) },
      ]);
    } finally {
      setActionBusy(null);
    }
  };

  const actionBlocked = (action: ModAction) =>
    actionParams(action).some((p) => p.required && p.type !== "bool" && isEmpty(values[p.name]));

  const blocked = disabled || missingRequired;
  const loose = visible.filter((p) => !p.section);
  const sections = mod.sections.filter((s) => sectionShown.get(s.id) !== false);
  const tabbed = mod.ui.layout === "tabs";
  const activeTab = sections.find((s) => s.id === tab)?.id ?? sections[0]?.id;

  const renderSection = (section: (typeof sections)[number]) => (
    <section key={section.id} className="space-y-3" aria-label={section.title}>
      {!tabbed && (
        <h3 className="border-b border-border/60 pb-1 text-sm font-semibold">{section.title}</h3>
      )}
      {section.text && <MarkdownLite text={section.text} className="text-muted-foreground" />}
      <ParamGrid
        params={visible.filter((p) => p.section === section.id)}
        values={values}
        onChange={setValue}
      />
    </section>
  );

  return (
    <div className="space-y-4">
      <ParamGrid params={loose} values={values} onChange={setValue} />

      {tabbed && sections.length > 0 ? (
        <div className="space-y-3">
          <div role="tablist" aria-label="Sections" className="flex flex-wrap gap-1 rounded-lg bg-muted p-1">
            {sections.map((s) => (
              <button
                key={s.id}
                type="button"
                role="tab"
                aria-selected={s.id === activeTab}
                onClick={() => setTab(s.id)}
                className={cn(
                  "rounded-md px-3 py-1 text-sm font-medium transition-colors",
                  s.id === activeTab ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {s.title}
              </button>
            ))}
          </div>
          {sections.filter((s) => s.id === activeTab).map(renderSection)}
        </div>
      ) : (
        sections.map(renderSection)
      )}

      {mod.actions.length > 0 && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {mod.actions.map((action) => (
              <Button
                key={action.name}
                type="button"
                variant="outline"
                title={action.help || undefined}
                disabled={actionBusy !== null || actionBlocked(action)}
                onClick={() => void runAction(action)}
              >
                {actionBusy === action.name ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Zap className="h-4 w-4" />
                )}
                {action.label}
              </Button>
            ))}
          </div>
          <ModResults results={actionResults} />
        </div>
      )}

      {formError && <p className="text-sm text-danger-text">{formError}</p>}
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
