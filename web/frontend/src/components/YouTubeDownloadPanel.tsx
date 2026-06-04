import { useMemo, useState } from "react";
import {
  CheckCircle2,
  Loader2,
  Plus,
  X,
  XCircle,
  Youtube,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { CheckField, Field, PathField, SelectField } from "@/components/fields";
import { Input } from "@/components/ui/input";
import type { ActiveJob, JobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

interface YouTubeDownloadPanelProps {
  jobs: ActiveJob[];
  onQueue: (params: Record<string, unknown>) => Promise<void>;
  onCancel: (jobId: string) => void;
  onDismissFinished: () => void;
}

const TERMINAL: JobStatus[] = ["completed", "failed", "cancelled"];

function shortUrl(url: string, max = 56): string {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, "");
    const rest = u.pathname + u.search;
    const full = host + rest;
    return full.length > max ? `${full.slice(0, max - 1)}…` : full;
  } catch {
    return url.length > max ? `${url.slice(0, max - 1)}…` : url;
  }
}

function statusLabel(status: JobStatus): string {
  switch (status) {
    case "queued":
      return "Queued";
    case "running":
      return "Downloading";
    case "completed":
      return "Complete";
    case "failed":
      return "Failed";
    case "cancelled":
      return "Cancelled";
  }
}

function StatusIcon({ status }: { status: JobStatus }) {
  if (status === "running" || status === "queued") {
    return <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />;
  }
  if (status === "completed") {
    return <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />;
  }
  return <XCircle className="h-4 w-4 shrink-0 text-muted-foreground" />;
}

function DownloadRow({
  job,
  onCancel,
}: {
  job: ActiveJob;
  onCancel: (id: string) => void;
}) {
  const active = job.status === "queued" || job.status === "running";
  const title =
    job.progressLabel?.split(" — ")[0]?.trim() ||
    (job.downloadMeta?.url ? shortUrl(job.downloadMeta.url) : `Job ${job.id.slice(0, 8)}`);
  const pct = job.progress ?? (job.status === "completed" ? 100 : null);

  return (
    <li className="flex gap-3 border-b px-3 py-3 last:border-b-0">
      <StatusIcon status={job.status} />
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium" title={job.downloadMeta?.url ?? title}>
              {title}
            </p>
            <p className="text-xs text-muted-foreground">
              {statusLabel(job.status)}
              {job.downloadMeta?.format ? ` · ${job.downloadMeta.format.toUpperCase()}` : ""}
              {job.progressLabel && active ? ` · ${job.progressLabel}` : ""}
            </p>
          </div>
          {active && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
              aria-label="Cancel download"
              onClick={() => onCancel(job.id)}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
        {(active || job.status === "completed") && pct != null && (
          <Progress value={Math.min(100, Math.max(0, pct))} className="h-1.5" />
        )}
        {job.status === "failed" && job.error && (
          <p className="text-xs text-red-600 dark:text-red-400">{job.error}</p>
        )}
      </div>
    </li>
  );
}

export function YouTubeDownloadPanel({
  jobs,
  onQueue,
  onCancel,
  onDismissFinished,
}: YouTubeDownloadPanelProps) {
  const [url, setUrl] = useState("");
  const [output, setOutput] = useState("");
  const [format, setFormat] = useState("mp4");
  const [quality, setQuality] = useState("best");
  const [bitrate, setBitrate] = useState("192");
  const [playlist, setPlaylist] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [queueing, setQueueing] = useState(false);

  const activeCount = useMemo(
    () => jobs.filter((j) => j.status === "queued" || j.status === "running").length,
    [jobs],
  );
  const finishedCount = useMemo(() => jobs.filter((j) => TERMINAL.includes(j.status)).length, [jobs]);

  const canQueue = Boolean(url.trim() && output.trim()) && !queueing;

  const queueDownload = async () => {
    if (!canQueue) return;
    setError(null);
    setQueueing(true);
    const queuedUrl = url.trim();
    try {
      await onQueue({
        url: queuedUrl,
        output,
        format,
        video_quality: quality,
        audio_bitrate: Number(bitrate),
        playlist,
        no_playlist_index: false,
      });
      setUrl("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setQueueing(false);
    }
  };

  return (
    <>
      <CardHeader className="space-y-3 pb-4">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-red-600 text-white shadow-sm">
            <Youtube className="h-6 w-6" />
          </div>
          <div className="space-y-1">
            <CardTitle className="text-xl">YouTube downloads</CardTitle>
            <CardDescription>
              Queue multiple videos or playlists at once. Powered by yt-dlp — works with YouTube and
              other supported sites.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <PathField
          label="Save to folder"
          value={output}
          onChange={setOutput}
          hint="All queued downloads use this folder."
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField
            label="Format"
            value={format}
            onChange={setFormat}
            options={[
              { value: "mp4", label: "MP4 video" },
              { value: "mp3", label: "MP3 audio" },
            ]}
          />
          <SelectField
            label="Max quality"
            value={quality}
            onChange={setQuality}
            options={["best", "2160", "1440", "1080", "720", "480", "360"].map((v) => ({
              value: v,
              label: v === "best" ? "Best" : `${v}p`,
            }))}
          />
        </div>
        {format === "mp3" && (
          <Field label="Audio bitrate (kbps)">
            <Input type="number" value={bitrate} onChange={(e) => setBitrate(e.target.value)} />
          </Field>
        )}
        <CheckField
          label="Playlist mode"
          checked={playlist}
          onChange={setPlaylist}
          hint="Download every item when the URL is a playlist."
        />

        <div className="space-y-2">
          <Field label="YouTube URL">
            <div className="flex gap-2">
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=…"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && canQueue) void queueDownload();
                }}
              />
              <Button
                type="button"
                size="lg"
                className="shrink-0 gap-1.5"
                disabled={!canQueue}
                onClick={() => void queueDownload()}
              >
                {queueing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
                Add
              </Button>
            </div>
          </Field>
          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        </div>

        <div className="overflow-hidden rounded-lg border bg-card">
          <div className="flex items-center justify-between gap-2 border-b bg-muted/50 px-3 py-2">
            <p className="text-sm font-medium">
              Downloads
              {jobs.length > 0 && (
                <span className="ml-1.5 font-normal text-muted-foreground">
                  ({activeCount} active{jobs.length !== activeCount ? `, ${jobs.length} total` : ""})
                </span>
              )}
            </p>
            {finishedCount > 0 && (
              <Button type="button" variant="ghost" size="sm" className="h-7 text-xs" onClick={onDismissFinished}>
                Clear finished
              </Button>
            )}
          </div>
          {jobs.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">
              No downloads yet. Paste a YouTube URL and click Add — you can queue more while others run.
            </p>
          ) : (
            <ul className={cn("max-h-[min(420px,50vh)] overflow-y-auto")}>
              {jobs.map((job) => (
                <DownloadRow key={job.id} job={job} onCancel={onCancel} />
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </>
  );
}
