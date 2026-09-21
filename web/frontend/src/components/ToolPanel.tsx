import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { CheckField, PathField, SelectField, ToolRunActions } from "@/components/fields";
import { ModForm } from "@/components/ModForm";
import { OrderedFileList, type FileListItem } from "@/components/OrderedFileList";
import { DownloadPanel } from "@/components/DownloadPanel";
import { RenameForm, type RenamedRoot } from "@/components/RenameForm";
import { SubtitleCleanupForm, SubtitleTranslateForm } from "@/components/SubtitlePanel";
import type { ActiveJob, DownloadJobMeta, ModInfo, ToolId, TranslationSample } from "@/lib/types";
import { fileExtension, normalizeFilePath, withFileExtension } from "@/lib/utils";

const OUTPUT_FORMAT_OPTS = [
  { value: "mp4", label: "MP4" },
  { value: "mkv", label: "MKV" },
  { value: "mov", label: "MOV" },
];

interface ToolPanelProps {
  tool: ToolId;
  /** The enabled mods; the tool is looked up here. */
  mods: ModInfo[];
  onRun: (params: Record<string, unknown>) => Promise<void>;
  onQueueDownloads?: (
    items: Array<{ params: Record<string, unknown>; downloadMeta: DownloadJobMeta }>,
  ) => Promise<void>;
  running: boolean;
  activeJob?: ActiveJob;
  downloadJobs?: ActiveJob[];
  onCancelDownload?: (jobId: string) => void;
  onDismissFinishedDownloads?: () => void;
  /** Set when the last rename also renamed the folder the user had selected. */
  renamedRoot?: RenamedRoot;
}

export function ToolPanel({
  tool,
  mods,
  onRun,
  onQueueDownloads,
  running,
  activeJob,
  downloadJobs = [],
  onCancelDownload,
  onDismissFinishedDownloads,
  renamedRoot,
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

  const mod = mods.find((m) => m.id === tool);
  if (!mod) {
    return (
      <Card className="border-0 shadow-md">
        <CardHeader>
          <CardTitle>Tool not available</CardTitle>
          <CardDescription>
            This tool is not loaded. It may be a mod that is turned off (Settings, Mods).
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

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
        <CardTitle>{mod.name}</CardTitle>
        <CardDescription>{mod.description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {mod.ui.kind === "form" ? (
          <ModForm key={mod.id} mod={mod} onRun={run} disabled={running} />
        ) : (
          <BuiltinPanel panel={mod.ui.panel} onRun={run} disabled={running} renamedRoot={renamedRoot} />
        )}

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        {activeJob && (
          <SubtitleJobStatus job={activeJob} />
        )}
      </CardContent>
    </Card>
  );
}

/** Tools whose form is too rich for a manifest (ordered file lists, profiles, review steps). */
function BuiltinPanel({
  panel,
  onRun,
  disabled,
  renamedRoot,
}: {
  panel: string;
  onRun: (p: Record<string, unknown>) => void;
  disabled?: boolean;
  renamedRoot?: RenamedRoot;
}) {
  switch (panel) {
    case "stitch":
      return <StitchForm onRun={onRun} disabled={disabled} />;
    case "rename":
      return <RenameForm onRun={onRun} disabled={disabled} renamedRoot={renamedRoot} />;
    case "subtitle_translate":
      return <SubtitleTranslateForm onRun={onRun} disabled={disabled} />;
    case "subtitle_cleanup":
      return <SubtitleCleanupForm onRun={onRun} disabled={disabled} />;
    default:
      return (
        <p className="text-sm text-muted-foreground">
          This tool needs a panel ({panel}) that this version of Toolbox does not have.
        </p>
      );
  }
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
