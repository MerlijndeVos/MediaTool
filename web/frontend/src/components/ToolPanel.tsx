import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { CheckField, Field, PathField, SelectField, ToolRunActions } from "@/components/fields";
import { Input } from "@/components/ui/input";
import { OrderedFileList, type FileListItem } from "@/components/OrderedFileList";
import { DownloadPanel } from "@/components/DownloadPanel";
import { RenameForm } from "@/components/RenameForm";
import { SubtitleCleanupForm, SubtitleTranslateForm } from "@/components/SubtitlePanel";
import type { ActiveJob, DownloadJobMeta, ToolId, TranslationSample } from "@/lib/types";
import { toolDescription, TOOL_LABELS } from "@/lib/types";
import { fileExtension, normalizeFilePath, withFileExtension } from "@/lib/utils";

const OUTPUT_FORMAT_OPTS = [
  { value: "mp4", label: "MP4" },
  { value: "mkv", label: "MKV" },
  { value: "mov", label: "MOV" },
];

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
const VIDEO_FORMAT_OPTS = [
  { value: "auto", label: "Auto (all videos)" },
  ...[
  "dv",
  "avi",
  "divx",
  "flv",
  "m2ts",
  "m4v",
  "mkv",
  "mov",
  "mp4",
  "mpeg",
  "mpg",
  "mts",
  "ogm",
  "ts",
  "vob",
  "webm",
  "wmv",
  ].map((ext) => ({ value: ext, label: ext.toUpperCase() })),
];

interface ToolPanelProps {
  tool: ToolId;
  onRun: (params: Record<string, unknown>) => Promise<void>;
  onQueueDownloads?: (
    items: Array<{ params: Record<string, unknown>; downloadMeta: DownloadJobMeta }>,
  ) => Promise<void>;
  running: boolean;
  activeJob?: ActiveJob;
  downloadJobs?: ActiveJob[];
  onCancelDownload?: (jobId: string) => void;
  onDismissFinishedDownloads?: () => void;
}

export function ToolPanel({
  tool,
  onRun,
  onQueueDownloads,
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

  const queueDownloads = async (
    items: Array<{ params: Record<string, unknown>; downloadMeta: DownloadJobMeta }>,
  ) => {
    if (!onQueueDownloads) return;
    setError(null);
    try {
      await onQueueDownloads(items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (tool === "download" && onCancelDownload && onDismissFinishedDownloads && onQueueDownloads) {
    return (
      <Card className="border-0 shadow-md">
        <DownloadPanel
          jobs={downloadJobs}
          onQueueDownloads={queueDownloads}
          onCancel={onCancelDownload}
          onDismissFinished={onDismissFinishedDownloads}
        />
        {error && <p className="px-6 pb-4 text-sm text-red-600 dark:text-red-400">{error}</p>}
      </Card>
    );
  }

  return (
    <Card className="border-0 shadow-md">
      <CardHeader>
        <CardTitle>{TOOL_LABELS[tool]}</CardTitle>
        <CardDescription>{toolDescription(tool)}</CardDescription>
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
        {tool === "subtitle_translate" && (
          <SubtitleTranslateForm onRun={run} disabled={running} />
        )}
        {tool === "subtitle_cleanup" && (
          <SubtitleCleanupForm onRun={run} disabled={running} />
        )}

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        {activeJob && (
          <SubtitleJobStatus job={activeJob} />
        )}
      </CardContent>
    </Card>
  );
}

function SubtitleJobStatus({ job }: { job: ActiveJob }) {
  const samples = job.translationSamples ?? [];
  const showSamples = job.command === "subtitle_translate" && samples.length > 0;
  const recentSamples = samples.slice(-6);

  return (
    <div className="space-y-3 rounded-lg border bg-muted/40 p-4">
      <div className="flex justify-between gap-3 text-sm">
        <span className="font-medium capitalize">{job.status}</span>
        <span className="text-right text-muted-foreground">{job.progressLabel ?? ""}</span>
      </div>
      {job.progress != null && job.status === "running" && (
        <Progress value={job.progress} />
      )}
      {job.status === "completed" && job.progress != null && (
        <Progress value={job.progress} />
      )}
      {showSamples && (
        <div className="space-y-2 border-t border-border/60 pt-3">
          <p className="text-sm font-medium">
            {job.status === "running" ? "Live translation samples" : "Translation samples"}
          </p>
          <div className="max-h-64 space-y-3 overflow-y-auto">
            {recentSamples.map((sample: TranslationSample, index) => (
              <div
                key={`${sample.source}-${index}`}
                className="space-y-1 rounded-md border border-border/60 bg-background/80 px-3 py-2 text-xs"
              >
                <p className="text-muted-foreground">{sample.source}</p>
                <p className="text-foreground">{sample.target}</p>
              </div>
            ))}
          </div>
          {samples.length > recentSamples.length && (
            <p className="text-xs text-muted-foreground">
              Showing the latest {recentSamples.length} of {samples.length} samples.
            </p>
          )}
        </div>
      )}
    </div>
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

  const runParams = (dryRun: boolean) => ({
    input,
    output,
    input_format: inputFormat,
    output_format: outputFormat,
    use_gpu: useGpu,
    deinterlace,
    crf: Number(crf),
    preset,
    dry_run: dryRun,
  });

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <PathField
          label="Input folder"
          value={input}
          onChange={setInput}
          tooltip="Root folder scanned recursively for source files."
        />
        <PathField
          label="Output folder"
          value={output}
          onChange={setOutput}
          tooltip="Converted files are written here, mirroring the input folder structure."
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField
          label="Input format"
          value={inputFormat}
          onChange={setInputFormat}
          tooltip="Auto converts every supported video in the folder. Or pick one extension to scan for."
          options={VIDEO_FORMAT_OPTS}
        />
        <SelectField
          label="Output format"
          value={outputFormat}
          onChange={setOutputFormat}
          tooltip="Container format for the converted files."
          options={[
            { value: "mp4", label: "MP4" },
            { value: "mkv", label: "MKV" },
            { value: "mov", label: "MOV" },
          ]}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField
          label="GPU"
          value={useGpu}
          onChange={setUseGpu}
          tooltip="Auto tries NVENC; On requires GPU encoding; Off uses CPU (libx264)."
          options={GPU_OPTS}
        />
        <SelectField
          label="Deinterlace"
          value={deinterlace}
          onChange={setDeinterlace}
          tooltip="Auto enables bwdif only for interlaced sources like DV."
          options={DEINTERLACE_OPTS}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="CRF"
          tooltip="Quality for CPU encoding. Lower means better quality and larger files (typical range 18–23)."
        >
          <Input type="number" value={crf} onChange={(e) => setCrf(e.target.value)} />
        </Field>
        <SelectField
          label="Preset"
          value={preset}
          onChange={setPreset}
          tooltip="Encoding speed vs compression. Slower presets squeeze more quality per bit."
          options={PRESETS.map((p) => ({ value: p, label: p }))}
        />
      </div>
      <ToolRunActions
        loading={disabled}
        disabled={disabled || !input || !output}
        onPreview={() => onRun(runParams(true))}
        onApply={() => onRun(runParams(false))}
      />
    </div>
  );
}

function TrimForm({ onRun, disabled }: { onRun: (p: Record<string, unknown>) => void; disabled?: boolean }) {
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [trimStart, setTrimStart] = useState("0");
  const [trimEnd, setTrimEnd] = useState("0");
  const [fmt, setFmt] = useState("auto");
  const [reencode, setReencode] = useState(false);
  const [replace, setReplace] = useState(false);
  const [noRec, setNoRec] = useState(false);

  const runParams = (dryRun: boolean) => ({
    input,
    output: output || null,
    trim_start: trimStart,
    trim_end: trimEnd,
    input_format: fmt,
    dry_run: dryRun,
    reencode,
    replace,
    no_recursive: noRec,
  });

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <PathField
          label="Input file or folder"
          value={input}
          onChange={setInput}
          tooltip="A single video file, or a folder of videos matching the format below."
        />
        <PathField
          label="Output folder (optional)"
          value={output}
          onChange={setOutput}
          placeholder="Leave empty for 'name - trimmed.ext'"
          tooltip="Leave empty to write each trimmed file next to its source as name - trimmed.ext."
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Trim start"
          tooltip="Seconds (10, 0.5), milliseconds (500ms), or a timestamp (0:10, 1:02:03)."
        >
          <Input
            value={trimStart}
            onChange={(e) => setTrimStart(e.target.value)}
            placeholder="0, 0.5, 500ms, 0:10"
          />
        </Field>
        <Field
          label="Trim end"
          tooltip="Seconds (5, 0.25), milliseconds (250ms), or a timestamp (0:05)."
        >
          <Input
            value={trimEnd}
            onChange={(e) => setTrimEnd(e.target.value)}
            placeholder="0, 0.25, 250ms, 0:05"
          />
        </Field>
      </div>
      <SelectField
        label="Folder format"
        value={fmt}
        onChange={setFmt}
        tooltip="When input is a folder, Auto trims every supported video. Or pick one extension."
        options={VIDEO_FORMAT_OPTS}
      />
      <CheckField
        label="Re-encode (frame-accurate)"
        checked={reencode}
        onChange={setReencode}
        tooltip="Re-encode for an exact cut. Off copies streams (faster, but snaps to keyframes)."
      />
      <CheckField
        label="Replace original"
        checked={replace}
        onChange={setReplace}
        tooltip="Overwrite each source with its trimmed version once the trim succeeds."
      />
      <CheckField
        label="No recursion"
        checked={noRec}
        onChange={setNoRec}
        tooltip="When input is a folder, only scan that folder, not subfolders."
      />
      <ToolRunActions
        loading={disabled}
        disabled={disabled || !input}
        onPreview={() => onRun(runParams(true))}
        onApply={() => onRun(runParams(false))}
      />
    </div>
  );
}

function StitchForm({ onRun, disabled }: { onRun: (p: Record<string, unknown>) => void; disabled?: boolean }) {
  const [parts, setParts] = useState<FileListItem[]>([]);
  const [output, setOutput] = useState("");
  const [outputFormat, setOutputFormat] = useState("mp4");
  const [reencode, setReencode] = useState(false);

  const hasMixedFormats = useMemo(() => {
    const exts = parts.map((part) => fileExtension(part.path)).filter(Boolean);
    return new Set(exts).size > 1;
  }, [parts]);

  useEffect(() => {
    if (hasMixedFormats) setReencode(true);
  }, [hasMixedFormats]);

  const handleOutputFormatChange = (format: string) => {
    setOutputFormat(format);
    if (output.trim()) setOutput(withFileExtension(output, format));
  };

  const runParams = (dryRun: boolean) => ({
    input: parts.map((part) => normalizeFilePath(part.path)),
    output: withFileExtension(output, outputFormat),
    output_format: outputFormat,
    dry_run: dryRun,
    reencode: hasMixedFormats || reencode,
    input_format: "mp4",
    no_recursive: false,
  });

  return (
    <div className="space-y-4">
      <OrderedFileList
        label="Parts to join"
        tooltip="Parts are joined in list order. Mixed formats turn on Re-encode automatically."
        items={parts}
        onChange={setParts}
        showFormat
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField
          label="Output format"
          value={outputFormat}
          onChange={handleOutputFormatChange}
          tooltip="Container for the joined video. The output path extension updates to match."
          options={OUTPUT_FORMAT_OPTS}
        />
        <PathField
          label="Output file"
          value={output}
          onChange={setOutput}
          placeholder={`C:\\out\\joined.${outputFormat}`}
          tooltip="Path for the combined file. Extension should match the output format above."
        />
      </div>
      <CheckField
        label="Re-encode"
        checked={reencode}
        onChange={setReencode}
        disabled={hasMixedFormats}
        hint={hasMixedFormats ? "Required when parts use different formats." : undefined}
        tooltip="Transcode to H.264 + AAC before joining. Locked on when formats in the list differ."
      />
      <ToolRunActions
        loading={disabled}
        disabled={disabled || parts.length < 2 || !output}
        onPreview={() => onRun(runParams(true))}
        onApply={() => onRun(runParams(false))}
      />
    </div>
  );
}

function VtsForm({ onRun, disabled }: { onRun: (p: Record<string, unknown>) => void; disabled?: boolean }) {
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [reencode, setReencode] = useState(false);
  const [minMb, setMinMb] = useState("50");

  const runParams = (dryRun: boolean) => ({
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
  });

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <PathField
          label="Input folder"
          value={input}
          onChange={setInput}
          tooltip="Folder with VIDEO_TS rips or VTS_xx_x.VOB files, scanned recursively."
        />
        <PathField
          label="Output folder"
          value={output}
          onChange={setOutput}
          tooltip="One joined file per DVD title is written here."
        />
      </div>
      <Field
        label="Min title size (MB)"
        tooltip="Skip title sets smaller than this (menus, junk). Use 0 to convert everything."
      >
        <Input type="number" value={minMb} onChange={(e) => setMinMb(e.target.value)} />
      </Field>
      <CheckField
        label="Re-encode to H.264"
        checked={reencode}
        onChange={setReencode}
        tooltip="Transcode to H.264 instead of a fast lossless remux. Slower, but smaller files."
      />
      <ToolRunActions
        loading={disabled}
        disabled={disabled || !input || !output}
        onPreview={() => onRun(runParams(true))}
        onApply={() => onRun(runParams(false))}
      />
    </div>
  );
}

function AudioForm({ onRun, disabled }: { onRun: (p: Record<string, unknown>) => void; disabled?: boolean }) {
  const [input, setInput] = useState("");
  const [lang, setLang] = useState("eng");
  const runParams = (apply: boolean) => ({
    input,
    lang,
    apply,
    set_language: false,
    no_recursive: false,
  });

  return (
    <div className="space-y-4">
      <PathField
        label="MKV file or folder"
        value={input}
        onChange={setInput}
        tooltip="An .mkv file or folder of MKV files, scanned recursively."
      />
      <Field
        label="Language"
        tooltip="Desired default audio track: 2-letter (en), 3-letter (eng), or name (english)."
      >
        <Input value={lang} onChange={(e) => setLang(e.target.value)} placeholder="eng" />
      </Field>
      <ToolRunActions
        loading={disabled}
        disabled={disabled || !input || !lang}
        applyHint="Remuxes MKV files with stream copy (no re-encode)."
        onPreview={() => onRun(runParams(false))}
        onApply={() => onRun(runParams(true))}
      />
    </div>
  );
}

function DedupForm({ onRun, disabled }: { onRun: (p: Record<string, unknown>) => void; disabled?: boolean }) {
  const [input, setInput] = useState("");

  return (
    <div className="space-y-4">
      <PathField
        label="Folder"
        value={input}
        onChange={setInput}
        tooltip="Scans recursively for files named like name (2).ext and renames them back to name.ext."
      />
      <ToolRunActions
        loading={disabled}
        disabled={disabled || !input}
        onPreview={() => onRun({ input, apply: false })}
        onApply={() => onRun({ input, apply: true })}
      />
    </div>
  );
}

function RenameFoldersForm({ onRun, disabled }: { onRun: (p: Record<string, unknown>) => void; disabled?: boolean }) {
  const [root, setRoot] = useState("");

  return (
    <div className="space-y-4">
      <PathField
        label="Root folder"
        value={root}
        onChange={setRoot}
        tooltip='Renames direct subfolders to "YYYY maand DD - Description" using dates from video filenames.'
      />
      <ToolRunActions
        loading={disabled}
        disabled={disabled || !root}
        onPreview={() => onRun({ root, dry_run: true })}
        onApply={() => onRun({ root, dry_run: false })}
      />
    </div>
  );
}
