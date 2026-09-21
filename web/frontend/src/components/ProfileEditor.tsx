import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Check, Loader2, Sparkles, Trash2, X } from "lucide-react";
import { generateRenameProfile, testRenameProfile, type RenameGenerateResult, type RenameTestResult } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CheckField, Field, SelectField } from "@/components/fields";
import {
  BRACKET_KINDS,
  CASE_OPTIONS,
  DATE_LOCALE_OPTIONS,
  DEFAULT_PATTERNS,
  PATTERN_LABELS,
  PATTERN_TOKENS,
  RULE_LABELS,
  newRule,
  parseExamples,
  tokenSnippet,
  type DateLocale,
  type PatternKey,
  type RenameMode,
  type RenameProfile,
  type RenameRule,
  type RuleType,
} from "@/lib/renameProfiles";
import { cn } from "@/lib/utils";

const SAMPLE_DEFAULTS: Record<RenameMode, string> = {
  media: "Show.Name.S01E02.Episode.Title.1080p.WEB-DL.x265-GRP.mkv\nSome.Movie.2008.1080p.BluRay.mkv",
  generic: "kick_drums_vol.1_[WAV]_free_download\nSnare Hits (2019)",
};

const AI_PLACEHOLDER: Record<RenameMode, string> = {
  media: "Breaking.Bad.S01E01.Pilot.1080p.mkv -> breaking bad - S01E01 - pilot.mkv",
  generic: "Cool_Pack.Vol.1_[WAV] -> Cool Pack Vol 1",
};

function WordsInput({ words, onChange }: { words: string[]; onChange: (w: string[]) => void }) {
  const [text, setText] = useState(words.join(", "));
  return (
    <Input
      value={text}
      placeholder="word, another word"
      onChange={(e) => {
        setText(e.target.value);
        onChange(
          e.target.value
            .split(",")
            .map((w) => w.trim())
            .filter(Boolean),
        );
      }}
    />
  );
}

function RuleRow({
  rule,
  index,
  count,
  onChange,
  onMove,
  onRemove,
}: {
  rule: RenameRule;
  index: number;
  count: number;
  onChange: (rule: RenameRule) => void;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-start gap-2 rounded-md border bg-card px-3 py-2">
      <span className="mt-2 w-5 shrink-0 text-xs tabular-nums text-muted-foreground">{index + 1}.</span>
      <div className="min-w-0 flex-1 space-y-1.5">
        <p className="text-xs font-medium text-muted-foreground">{RULE_LABELS[rule.type]}</p>
        {rule.type === "replace" && (
          <div className="grid gap-2 sm:grid-cols-2">
            <Input
              value={rule.find ?? ""}
              placeholder="Find (e.g. .)"
              onChange={(e) => onChange({ ...rule, find: e.target.value })}
            />
            <Input
              value={rule.with ?? ""}
              placeholder="Replace with (space, or empty to delete)"
              onChange={(e) => onChange({ ...rule, with: e.target.value })}
            />
          </div>
        )}
        {rule.type === "remove_words" && (
          <WordsInput words={rule.words ?? []} onChange={(words) => onChange({ ...rule, words })} />
        )}
        {rule.type === "remove_brackets" && (
          <div className="flex flex-wrap gap-2">
            {BRACKET_KINDS.map((b) => {
              const on = rule.brackets?.includes(b.value) ?? false;
              return (
                <button
                  key={b.value}
                  type="button"
                  onClick={() => {
                    const cur = rule.brackets ?? [];
                    const next = on ? cur.filter((k) => k !== b.value) : [...cur, b.value];
                    onChange({ ...rule, brackets: next });
                  }}
                  className={cn(
                    "rounded-md border px-3 py-1 font-mono text-sm transition-colors",
                    on ? "border-primary bg-primary/10 text-foreground" : "border-border text-muted-foreground",
                  )}
                >
                  {b.label}
                </button>
              );
            })}
            <span className="self-center text-xs text-muted-foreground">
              Removes the brackets and everything inside them.
            </span>
          </div>
        )}
        {rule.type === "case" && (
          <select
            value={rule.mode ?? "title"}
            onChange={(e) => onChange({ ...rule, mode: e.target.value })}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm sm:w-56"
          >
            {CASE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        )}
        {rule.type === "prune_date" && (
          <p className="text-xs text-muted-foreground">
            Removes dates like 2006, 13 juli 2006 or 2006-07-13 from the name, so a date only appears where the
            pattern puts it.
          </p>
        )}
        {rule.type === "regex_replace" && (
          <div className="grid gap-2 sm:grid-cols-2">
            <Input
              value={rule.pattern ?? ""}
              placeholder="Regex, e.g. \s*v\d+$"
              className="font-mono"
              onChange={(e) => onChange({ ...rule, pattern: e.target.value })}
            />
            <Input
              value={rule.with ?? ""}
              placeholder="Replace with"
              onChange={(e) => onChange({ ...rule, with: e.target.value })}
            />
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center">
        <Button type="button" variant="ghost" size="icon" className="h-8 w-8" disabled={index === 0} onClick={() => onMove(-1)} aria-label="Move up">
          <ArrowUp className="h-3.5 w-3.5" />
        </Button>
        <Button type="button" variant="ghost" size="icon" className="h-8 w-8" disabled={index === count - 1} onClick={() => onMove(1)} aria-label="Move down">
          <ArrowDown className="h-3.5 w-3.5" />
        </Button>
        <Button type="button" variant="ghost" size="icon" className="h-8 w-8 hover:text-destructive" onClick={onRemove} aria-label="Remove rule">
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

function PatternInput({
  patternKey,
  value,
  onChange,
}: {
  patternKey: PatternKey;
  value: string;
  onChange: (v: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <Field
      label={PATTERN_LABELS[patternKey]}
      hint={`Default: ${DEFAULT_PATTERNS[patternKey]}`}
      tooltip="Build the output name from tokens. :02 zero-pads numbers; :upper, :lower and :title change case. Empty tokens are dropped with the separators around them."
    >
      <Input
        ref={inputRef}
        value={value}
        placeholder={DEFAULT_PATTERNS[patternKey]}
        className="font-mono"
        onChange={(e) => onChange(e.target.value)}
      />
      <div className="flex flex-wrap gap-1.5 pt-1.5">
        {PATTERN_TOKENS[patternKey].map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => {
              onChange(`${value || DEFAULT_PATTERNS[patternKey]}${tokenSnippet(t)}`);
              inputRef.current?.focus();
            }}
            className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            title={`Append ${tokenSnippet(t)}`}
          >
            {`{${t}}`}
          </button>
        ))}
      </div>
      {patternKey === "generic" && (
        <p className="pt-1 text-xs text-muted-foreground">
          <code className="rounded bg-muted px-1">{"{date}"}</code> is the earliest date in the video file names inside
          each folder (DV <em>clip-2006-07-13</em> or MP4 <em>13 juli 2006</em> names). Choose its format after a colon, for
          example <code className="rounded bg-muted px-1">{"{date:YYYY MMMM D}"}</code>: YYYY year, MMMM month name, MMM
          short name, MM month, DD day (D without a leading zero). Folders with no date are skipped.
        </p>
      )}
    </Field>
  );
}

interface ProfileEditorProps {
  mode: RenameMode;
  profile: RenameProfile;
  onChange: (profile: RenameProfile) => void;
}

export function ProfileEditor({ mode, profile, onChange }: ProfileEditorProps) {
  const [samples, setSamples] = useState(SAMPLE_DEFAULTS[mode]);
  const [results, setResults] = useState<RenameTestResult[]>([]);
  const [testError, setTestError] = useState<string | null>(null);

  const [examples, setExamples] = useState("");
  const [generating, setGenerating] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiResult, setAiResult] = useState<RenameGenerateResult | null>(null);

  // Reset the sample box when the mode changes.
  useEffect(() => {
    setSamples(SAMPLE_DEFAULTS[mode]);
    setAiResult(null);
    setAiError(null);
  }, [mode]);

  // Live preview of the profile on sample names (debounced).
  const profileKey = useMemo(() => JSON.stringify(profile), [profile]);
  useEffect(() => {
    const list = samples.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 20);
    if (list.length === 0) {
      setResults([]);
      return;
    }
    const handle = setTimeout(() => {
      testRenameProfile(profile, mode, list)
        .then((r) => {
          setResults(r.results);
          setTestError(null);
        })
        .catch((e) => setTestError(e instanceof Error ? e.message : String(e)));
    }, 350);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileKey, samples, mode]);

  const patch = (changes: Partial<RenameProfile>) => onChange({ ...profile, ...changes });
  const setRule = (i: number, rule: RenameRule) =>
    patch({ rules: profile.rules.map((r, idx) => (idx === i ? rule : r)) });
  const moveRule = (i: number, delta: -1 | 1) => {
    const rules = [...profile.rules];
    [rules[i], rules[i + delta]] = [rules[i + delta], rules[i]];
    patch({ rules });
  };
  const setPattern = (key: PatternKey, value: string) =>
    patch({ patterns: { ...profile.patterns, [key]: value } });

  const parsedExamples = parseExamples(examples);

  const generate = async () => {
    setGenerating(true);
    setAiError(null);
    setAiResult(null);
    try {
      const result = await generateRenameProfile(mode, parsedExamples);
      setAiResult(result);
      // Use the AI profile as the working draft; its suggested name is kept unless edited.
      onChange({ ...result.profile, id: undefined, builtin: false });
    } catch (e) {
      setAiError(e instanceof Error ? e.message : String(e));
    } finally {
      setGenerating(false);
    }
  };

  const patternKeys: PatternKey[] = mode === "media" ? ["tv", "movie"] : ["generic"];
  const usesDates =
    mode === "generic" &&
    ((profile.patterns.generic ?? "").includes("{date") || profile.rules.some((r) => r.type === "prune_date"));

  return (
    <div className="space-y-5 rounded-lg border bg-muted/20 p-4">
      {/* AI helper */}
      <div className="space-y-2 rounded-md border border-primary/30 bg-primary/5 p-3">
        <p className="flex items-center gap-1.5 text-sm font-medium">
          <Sparkles className="h-4 w-4 text-primary" />
          Create a profile from an example
        </p>
        <p className="text-xs text-muted-foreground">
          One example per line as <code className="rounded bg-muted px-1">before -&gt; after</code>. The AI writes the rules and a
          name; nothing is renamed. It is checked against your examples below.
        </p>
        <textarea
          value={examples}
          onChange={(e) => setExamples(e.target.value)}
          placeholder={AI_PLACEHOLDER[mode]}
          rows={3}
          className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" size="sm" disabled={generating || parsedExamples.length === 0} onClick={() => void generate()}>
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Generate profile
          </Button>
          {parsedExamples.length > 0 && (
            <span className="text-xs text-muted-foreground">
              {parsedExamples.length} example{parsedExamples.length !== 1 ? "s" : ""} recognised
            </span>
          )}
        </div>
        {aiError && (
          <p className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-700 dark:text-red-300">{aiError}</p>
        )}
        {aiResult && (
          <div className="space-y-1 text-xs">
            <p className={aiResult.all_ok ? "text-emerald-700 dark:text-emerald-400" : "text-amber-700 dark:text-amber-400"}>
              {aiResult.all_ok
                ? `Profile "${aiResult.profile.name}" reproduces all examples. Review it below, then save it.`
                : "The AI could not reproduce every example. Adjust the rules below or reword the example."}
            </p>
            {aiResult.verification.map((v, i) => (
              <p key={i} className="flex items-start gap-1.5 font-mono">
                {v.ok ? (
                  <Check className="mt-0.5 h-3 w-3 shrink-0 text-emerald-600" />
                ) : (
                  <X className="mt-0.5 h-3 w-3 shrink-0 text-red-600" />
                )}
                <span className="min-w-0 break-all">
                  {v.ok ? v.expected : `${v.actual ?? "(not recognised)"}  (expected: ${v.expected})`}
                </span>
              </p>
            ))}
          </div>
        )}
      </div>

      <Field label="Profile name">
        <Input value={profile.name} onChange={(e) => patch({ name: e.target.value })} />
      </Field>

      {mode === "media" && (
        <CheckField
          label="Remove release tags"
          checked={profile.strip_release_junk}
          onChange={(v) => patch({ strip_release_junk: v })}
          tooltip="Strips tags like 1080p, WEB-DL, x265 and scene group names from titles. Dots and underscores always become spaces in this mode."
        />
      )}

      {/* Rules */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium">Cleanup rules</p>
          <select
            value=""
            onChange={(e) => {
              if (e.target.value) patch({ rules: [...profile.rules, newRule(e.target.value as RuleType)] });
            }}
            className="h-8 rounded-md border border-input bg-background px-2 text-xs"
            aria-label="Add rule"
          >
            <option value="">+ Add rule…</option>
            {(Object.keys(RULE_LABELS) as RuleType[]).map((t) => (
              <option key={t} value={t}>
                {RULE_LABELS[t]}
              </option>
            ))}
          </select>
        </div>
        <p className="text-xs text-muted-foreground">Applied top to bottom to each name. Extra spaces and edge dashes/dots are tidied automatically.</p>
        {profile.rules.length === 0 ? (
          <p className="rounded-md border border-dashed px-3 py-4 text-center text-xs text-muted-foreground">
            No rules: names are only tidied. Add one with “+ Add rule”.
          </p>
        ) : (
          <div className="space-y-2">
            {profile.rules.map((rule, i) => (
              <RuleRow
                key={`${profile.id ?? "new"}-${i}-${rule.type}`}
                rule={rule}
                index={i}
                count={profile.rules.length}
                onChange={(r) => setRule(i, r)}
                onMove={(d) => moveRule(i, d)}
                onRemove={() => patch({ rules: profile.rules.filter((_, idx) => idx !== i) })}
              />
            ))}
          </div>
        )}
      </div>

      {/* Patterns */}
      <div className="grid gap-4 sm:grid-cols-2">
        {patternKeys.map((key) => (
          <PatternInput key={key} patternKey={key} value={profile.patterns[key] ?? ""} onChange={(v) => setPattern(key, v)} />
        ))}
      </div>

      {usesDates && (
        <div className="max-w-xs">
          <SelectField
            label="Month names"
            value={profile.date_locale ?? "en"}
            onChange={(v) => patch({ date_locale: v as DateLocale })}
            options={DATE_LOCALE_OPTIONS}
            tooltip="The language of month names for {date:MMMM} and for the “Remove dates from name” rule."
          />
        </div>
      )}

      {/* Tester */}
      <div className="space-y-2">
        <p className="text-sm font-medium">Try it</p>
        <textarea
          value={samples}
          onChange={(e) => setSamples(e.target.value)}
          rows={3}
          className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Sample names"
        />
        {testError && <p className="text-xs text-red-600 dark:text-red-400">{testError}</p>}
        {results.length > 0 && (
          <div className="overflow-hidden rounded-md border bg-card text-xs">
            {results.map((r, i) => (
              <div key={i} className="grid gap-x-3 border-b px-3 py-1.5 last:border-b-0 sm:grid-cols-2">
                <span className="break-all font-mono text-muted-foreground">{r.sample}</span>
                <span className={cn("break-all font-mono", r.result ? "text-foreground" : "text-amber-700 dark:text-amber-400")}>
                  {r.result ?? r.note ?? "—"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
