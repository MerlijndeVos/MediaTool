export type CommandName =
  | "convert"
  | "vts"
  | "rename"
  | "audio"
  | "dedup"
  | "download"
  | "trim"
  | "stitch"
  | "rename_folders";

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
}

export interface JobCreateResponse {
  job: JobSummary;
  events_url: string;
}

export interface LogLine {
  jobId: string;
  message: string;
  level: number;
  ts: number;
}

export interface ActiveJob extends JobSummary {
  logs: LogLine[];
  progress?: number | null;
  progressLabel?: string;
}

export type ToolId = CommandName;

export const PRIMARY_TOOLS: ToolId[] = ["convert", "trim", "stitch", "download"];
export const SECONDARY_TOOLS: ToolId[] = [
  "vts",
  "rename",
  "audio",
  "dedup",
  "rename_folders",
];

export const TOOL_LABELS: Record<ToolId, string> = {
  convert: "Convert",
  trim: "Trim",
  stitch: "Stitch",
  download: "Download",
  vts: "DVD (VTS)",
  rename: "Rename Media",
  audio: "Audio Default",
  dedup: "Fix Duplicates",
  rename_folders: "Rename Folders",
};
