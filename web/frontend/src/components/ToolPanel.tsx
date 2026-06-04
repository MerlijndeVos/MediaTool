import { useState } from "react";
import { Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { CheckField, DEFAULT_DRY_RUN, DryRunField, Field, PathField, SelectField } from "@/components/fields";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { YouTubeDownloadPanel } from "@/components/YouTubeDownloadPanel";
import type { ActiveJob, ToolId } from "@/lib/types";
import { TOOL_LABELS } from "@/lib/types";

const GPU_OPTS = [
  { value: "auto", label: "Auto" },
  { value: "on", label: "On" },
  { value: "off", label: "Off" },
];
const DEINTERLACE_OPTS = [
  { value: "auto", label: "Auto" },
  { value: "on", label: "On" },
  { value: "off", label: "Off" },
];
const PRESETS = [
  "ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "placebo",
];

interface ToolPanelProps {
  tool: ToolId;
  onRun: (params: Record<string, unknown>) => Promise<void>;
  running: boolean;
  activeJob?: ActiveJob;
  downloadJobs?: ActiveJob[];
  onCancelDownload?: (jobId: string) => void;
  onDismissFinishedDownloads?: () => void;
}

export function ToolPanel({
  tool,
  onRun,
  running,
  activeJob,
  downloadJobs = [],
  onCancelDownload,
  onDismissFinishedDownloads,
}: ToolPanelProps) {
  const [error, setError] = useState<string | null>(null);

  const run = async (params: Record<string, unknown>) => {
    setError(null);
    try {
      await onRun(params);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (tool === "download" && onCancelDownload && onDismissFinishedDownloads) {
    return (
      <Card className="border-0 shadow-md">
        <YouTubeDownloadPanel
          jobs={downloadJobs}
          onQueue={run}
          onCancel={onCancelDownload}
          onDismissFinished={onDismissFinishedDownloads}
        />
      </Card>
    );
  }

  return (
    <Card className="border-0 shadow-md">
      <CardHeader>
        <CardTitle>{TOOL_LABELS[tool]}</CardTitle>
        <CardDescription>All processing runs locally on your machine.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {tool === "convert" && <ConvertForm onRun={run} disabled={running} />}
        {tool === "trim" && <TrimForm onRun={run} disabled={running} />}
        {tool === "stitch" && <StitchForm onRun={run} disabled={running} />}
        {tool === "vts" && <VtsForm onRun={run} disabled={running} />}
        {tool === "rename" && <RenameForm onRun={run} disabled={running} />}
        {tool === "audio" && <AudioForm onRun={run} disabled={running} />}
        {tool === "dedup" && <DedupForm onRun={run} disabled={running} />}
        {tool === "rename_folders" && <RenameFoldersForm onRun={run} disabled={running} />}

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        {activeJob && (
          <div className="space-y-2 rounded-lg border bg-muted/40 p-4">
            <div className="flex justify-between text-sm">
              <span className="font-medium capitalize">{activeJob.status}</span>
              <span className="text-muted-foreground">{activeJob.progressLabel ?? ""}</span>
            </div>
            {activeJob.progress != null && <Progress value={activeJob.progress} />}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RunBar({
  onClick,
  disabled,
  loading,
  dryRun,
  label,
}: {
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
  dryRun: boolean;
  label?: string;
}) {
  const runLabel = label ?? (dryRun ? "Run preview" : "Apply changes");
  return (
    <Button
      onClick={onClick}
      disabled={disabled}
      variant={dryRun ? "secondary" : "default"}
      className={cn(
        "w-full sm:w-auto",
        dryRun && "border-amber-500/50 bg-amber-500/15 text-amber-950 hover:bg-amber-500/25 dark:text-amber-50",
        !dryRun && "shadow-sm",
      )}
      size="lg"
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
      {runLabel}
    </Button>
  );
}

function ConvertForm({
  onRun,
  disabled,
}: {
  onRun: (p: Record<string, unknown>) => void;
  disabled?: boolean;
}) {
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [inputFormat, setInputFormat] = useState("dv");
  const [outputFormat, setOutputFormat] = useState("mp4");
  const [useGpu, setUseGpu] = useState("auto");
  const [deinterlace, setDeinterlace] = useState("auto");
  const [crf, setCrf] = useState("19");
  const [preset, setPreset] = useState("slow");
  const [dryRun, setDryRun] = useState(DEFAULT_DRY_RUN);
  const [prune, setPrune] = useState(false);
  const [useful, setUseful] = useState(false);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <PathField label="Input folder" value={input} onChange={setInput} />
        <PathField label="Output folder" value={output} onChange={setOutput} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Input format">
          <Input value={inputFormat} onChange={(e) => setInputFormat(e.target.value)} placeholder="dv" />
        </Field>
        <SelectField label="Output format" value={outputFormat} onChange={setOutputFormat} options={[
          { value: "mp4", label: "MP4" },
          { value: "mkv", label: "MKV" },
          { value: "mov", label: "MOV" },
        ]} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField label="GPU" value={useGpu} onChange={setUseGpu} options={GPU_OPTS} />
        <SelectField label="Deinterlace" value={deinterlace} onChange={setDeinterlace} options={DEINTERLACE_OPTS} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="CRF">
          <Input type="number" value={crf} onChange={(e) => setCrf(e.target.value)} />
        </Field>
        <SelectField label="Preset" value={preset} onChange={setPreset} options={PRESETS.map((p) => ({ value: p, label: p }))} />
      </div>
      <CheckField label="Prune non-matching from output" checked={prune} onChange={setPrune} />
      <CheckField label="Copy useful-only tree" checked={useful} onChange={setUseful} />
      <DryRunField dryRun={dryRun} onChange={setDryRun} />
      <RunBar
        dryRun={dryRun}
        loading={disabled}
        disabled={disabled || !input || !output}
        onClick={() =>
          onRun({
            input,
            output,
            input_format: inputFormat,
            output_format: outputFormat,
            use_gpu: useGpu,
            deinterlace,
            crf: Number(crf),
            preset,
            dry_run: dryRun,
            prune_output: prune,
            copy_useful_only: useful,
          })
        }
      />
    </div>
  );
}

function TrimForm({ onRun, disabled }: { onRun: (p: Record<string, unknown>) => void; disabled?: boolean }) {
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [trimStart, setTrimStart] = useState("0");
  const [trimEnd, setTrimEnd] = useState("0");
  const [fmt, setFmt] = useState("mp4");
  const [dryRun, setDryRun] = useState(DEFAULT_DRY_RUN);
  const [reencode, setReencode] = useState(false);
  const [replace, setReplace] = useState(false);
  const [noRec, setNoRec] = useState(false);

  return (
    <div className="space-y-4">
      <PathField label="Input file or folder" value={input} onChange={setInput} />
      <PathField label="Output folder (optional)" value={output} onChange={setOutput} placeholder="Leave empty for 'name - trimmed.ext'" />
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Trim start (sec or 0:10)">
          <Input value={trimStart} onChange={(e) => setTrimStart(e.target.value)} />
        </Field>
        <Field label="Trim end">
          <Input value={trimEnd} onChange={(e) => setTrimEnd(e.target.value)} />
        </Field>
        <Field label="Folder format">
          <Input value={fmt} onChange={(e) => setFmt(e.target.value)} />
        </Field>
      </div>
      <CheckField label="Re-encode (frame-accurate)" checked={reencode} onChange={setReencode} />
      <CheckField label="Replace original" checked={replace} onChange={setReplace} hint="Overwrites source when trim succeeds." />
      <CheckField label="No recursion" checked={noRec} onChange={setNoRec} />
      <DryRunField dryRun={dryRun} onChange={setDryRun} />
      <RunBar
        dryRun={dryRun}
        loading={disabled}
        disabled={disabled || !input}
        onClick={() =>
          onRun({
            input,
            output: output || null,
            trim_start: trimStart,
            trim_end: trimEnd,
            input_format: fmt,
            dry_run: dryRun,
            reencode,
            replace,
            no_recursive: noRec,
          })
        }
      />
    </div>
  );
}

function StitchForm({ onRun, disabled }: { onRun: (p: Record<string, unknown>) => void; disabled?: boolean }) {
  const [parts, setParts] = useState<string[]>(["", ""]);
  const [output, setOutput] = useState("");
  const [dryRun, setDryRun] = useState(DEFAULT_DRY_RUN);
  const [reencode, setReencode] = useState(false);

  const setPart = (i: number, v: string) => {
    setParts((prev) => prev.map((p, j) => (j === i ? v : p)));
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">Parts in order (full paths):</p>
      {parts.map((p, i) => (
        <PathField key={i} label={`Part ${i + 1}`} value={p} onChange={(v) => setPart(i, v)} placeholder="C:\\path\\part.mp4" />
      ))}
      <Button variant="outline" size="sm" onClick={() => setParts((prev) => [...prev, ""])}>
        Add part
      </Button>
      <PathField label="Output file" value={output} onChange={setOutput} placeholder="C:\\out\\joined.mp4" />
      <CheckField label="Re-encode" checked={reencode} onChange={setReencode} />
      <DryRunField dryRun={dryRun} onChange={setDryRun} />
      <RunBar
        dryRun={dryRun}
        loading={disabled}
        disabled={disabled || parts.filter(Boolean).length < 2 || !output}
        onClick={() =>
          onRun({
            input: parts.filter(Boolean),
            output,
            dry_run: dryRun,
            reencode,
            input_format: "mp4",
            no_recursive: false,
          })
        }
      />
    </div>
  );
}

function VtsForm({ onRun, disabled }: { onRun: (p: Record<string, unknown>) => void; disabled?: boolean }) {
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [dryRun, setDryRun] = useState(DEFAULT_DRY_RUN);
  const [reencode, setReencode] = useState(false);
  const [minMb, setMinMb] = useState("50");

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <PathField label="Input folder" value={input} onChange={setInput} />
        <PathField label="Output folder" value={output} onChange={setOutput} />
      </div>
      <Field label="Min title size (MB)">
        <Input type="number" value={minMb} onChange={(e) => setMinMb(e.target.value)} />
      </Field>
      <CheckField label="Re-encode to H.264" checked={reencode} onChange={setReencode} />
      <DryRunField dryRun={dryRun} onChange={setDryRun} />
      <RunBar
        dryRun={dryRun}
        loading={disabled}
        disabled={disabled || !input || !output}
        onClick={() =>
          onRun({
            input,
            output,
            dry_run: dryRun,
            reencode,
            min_mb: Number(minMb),
            output_format: "mkv",
            deinterlace: "auto",
            use_gpu: "auto",
            crf: 19,
            preset: "slow",
            include_menus: false,
          })
        }
      />
    </div>
  );
}

function RenameForm({ onRun, disabled }: { onRun: (p: Record<string, unknown>) => void; disabled?: boolean }) {
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [dryRun, setDryRun] = useState(DEFAULT_DRY_RUN);
  const [copy, setCopy] = useState(false);
  const [undo, setUndo] = useState(false);

  return (
    <div className="space-y-4">
      <PathField label="Input folder" value={input} onChange={setInput} />
      <PathField label="Output (optional)" value={output} onChange={setOutput} hint="Leave empty to reorganize in place." />
      <CheckField label="Copy instead of move" checked={copy} onChange={setCopy} />
      <CheckField label="Undo last apply" checked={undo} onChange={setUndo} />
      <DryRunField dryRun={dryRun} onChange={setDryRun} />
      <RunBar
        dryRun={dryRun}
        loading={disabled}
        disabled={disabled || !input}
        onClick={() =>
          onRun({
            input,
            output: output || null,
            apply: !dryRun,
            copy,
            undo,
            type: "auto",
            prune_empty_dirs: false,
            no_titlecase: false,
            strip_words: [],
            bare_episode_numbers: false,
          })
        }
      />
    </div>
  );
}

function AudioForm({ onRun, disabled }: { onRun: (p: Record<string, unknown>) => void; disabled?: boolean }) {
  const [input, setInput] = useState("");
  const [lang, setLang] = useState("eng");
  const [dryRun, setDryRun] = useState(DEFAULT_DRY_RUN);

  return (
    <div className="space-y-4">
      <PathField label="MKV file or folder" value={input} onChange={setInput} />
      <Field label="Language">
        <Input value={lang} onChange={(e) => setLang(e.target.value)} placeholder="eng" />
      </Field>
      <DryRunField dryRun={dryRun} onChange={setDryRun} hint="Apply mode requires MKVToolNix on PATH." />
      <RunBar
        dryRun={dryRun}
        loading={disabled}
        disabled={disabled || !input || !lang}
        onClick={() => onRun({ input, lang, apply: !dryRun, set_language: false, no_recursive: false })}
      />
    </div>
  );
}

function DedupForm({ onRun, disabled }: { onRun: (p: Record<string, unknown>) => void; disabled?: boolean }) {
  const [input, setInput] = useState("");
  const [dryRun, setDryRun] = useState(DEFAULT_DRY_RUN);

  return (
    <div className="space-y-4">
      <PathField label="Folder" value={input} onChange={setInput} />
      <DryRunField dryRun={dryRun} onChange={setDryRun} />
      <RunBar dryRun={dryRun} loading={disabled} disabled={disabled || !input} onClick={() => onRun({ input, apply: !dryRun })} />
    </div>
  );
}

function RenameFoldersForm({ onRun, disabled }: { onRun: (p: Record<string, unknown>) => void; disabled?: boolean }) {
  const [root, setRoot] = useState("");
  const [dryRun, setDryRun] = useState(DEFAULT_DRY_RUN);

  return (
    <div className="space-y-4">
      <PathField label="Root folder" value={root} onChange={setRoot} />
      <DryRunField dryRun={dryRun} onChange={setDryRun} />
      <RunBar dryRun={dryRun} loading={disabled} disabled={disabled || !root} onClick={() => onRun({ root, dry_run: dryRun })} />
    </div>
  );
}
