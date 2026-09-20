export type CommandName =
  | "convert"
  | "vts"
  | "rename"
  | "audio"
  | "dedup"
  | "download"
  | "trim"
  | "stitch"
  | "rename_folders"
  | "subtitle_translate"
  | "subtitle_cleanup";

export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface JobSummary {
  id: string;
  command: CommandName;
  status: JobStatus;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  exit_code?: number | null;
  undo_available?: boolean;
  undo_used?: boolean;
  undo_op_count?: number | null;
  undo_of?: string | null;
}

export interface JobCreateResponse {
  job: JobSummary;
  events_url: string;
}

export interface JobUndoResponse {
  job: JobSummary;
  events_url: string;
  source_job_id: string;
}

export interface LogLine {
  jobId: string;
  message: string;
  level: number;
  ts: number;
}

export interface DownloadJobMeta {
  url: string;
  format: string;
  output: string;
  displayName?: string;
  expectedSize?: number | null;
}

export interface StartJobRequest {
  params: Record<string, unknown>;
  downloadMeta?: DownloadJobMeta;
}

export interface DownloadProgress {
  pct?: number | null;
  downloaded?: number | null;
  total?: number | null;
  speed?: number | null;
  eta?: number | null;
  status?: string;
  title?: string;
}

export interface TranslationSample {
  source: string;
  target: string;
}

export interface ActiveJob extends JobSummary {
  logs: LogLine[];
  progress?: number | null;
  progressLabel?: string;
  downloadMeta?: DownloadJobMeta;
  downloadProgress?: DownloadProgress;
  translationSamples?: TranslationSample[];
}

export interface DownloadProbeEntry {
  id: string;
  title: string;
  url: string;
  duration?: number | null;
  filesize?: number | null;
  playlist_index: number;
}

export interface DownloadProbeResult {
  url: string;
  is_playlist: boolean;
  playlist_title?: string | null;
  entries: DownloadProbeEntry[];
}

export type ToolId = CommandName;

export const PRIMARY_TOOLS: ToolId[] = ["convert", "trim", "stitch", "download", "rename"];
export const SUBTITLE_TOOLS: ToolId[] = ["subtitle_translate", "subtitle_cleanup"];
export const SECONDARY_TOOLS: ToolId[] = ["vts", "audio", "dedup", "rename_folders"];

export const TOOL_LABELS: Record<ToolId, string> = {
  convert: "Convert",
  trim: "Trim",
  stitch: "Stitch",
  download: "Download",
  vts: "DVD (VTS)",
  rename: "Rename",
  audio: "Audio Default",
  dedup: "Fix Duplicates",
  rename_folders: "Rename Folders",
  subtitle_translate: "Translate",
  subtitle_cleanup: "Clean Up",
};

export const TOOL_DESCRIPTIONS: Record<ToolId, string> = {
  convert: "Batch-convert videos between formats with optional deinterlace and GPU encoding.",
  trim: "Remove seconds from the start and/or end of one or more files.",
  stitch: "Join multiple clips into a single output file in order.",
  download: "Download videos or playlists from yt-dlp-supported sites as MP4 or MP3.",
  rename: "Organize TV shows and movies for Plex/Jellyfin, or clean up any folder and file names, using reusable format profiles.",
  vts: "Merge DVD VIDEO_TS VOB files into one file per title.",
  audio: "Set the default audio track language in MKV files (ffmpeg stream copy).",
  dedup: "Remove duplicate (2), (3), … suffixes from filenames.",
  rename_folders: "Rename subfolders to YYYY month DD - Description using video dates.",
  subtitle_translate: "Translate SRT subtitles to another language with OpenAI.",
  subtitle_cleanup: "Remove URLs, credits, and other junk lines from SRT files in place.",
};

export function toolDescription(tool: ToolId): string {
  return TOOL_DESCRIPTIONS[tool];
}
