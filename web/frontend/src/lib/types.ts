/** A mod id: built-in features and user mods are all addressed by id. */
export type CommandName = string;

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

export type ModParamType =
  | "text"
  | "number"
  | "integer"
  | "bool"
  | "choice"
  | "folder"
  | "file"
  | "files"
  | "list"
  | "json";

export interface ModParam {
  name: string;
  type: ModParamType;
  label: string;
  help: string;
  placeholder: string;
  required: boolean;
  default?: unknown;
  /** Value the form starts with when it differs from the API default. */
  initial?: unknown;
  choices: { value: string; label: string }[];
  strict: boolean;
  min?: number | null;
  max?: number | null;
  ui: boolean;
  width: "full" | "half";
  nullable: boolean;
}

export interface ModInfo {
  id: string;
  name: string;
  description: string;
  version: string;
  author: string;
  group: string;
  order: number;
  icon: string;
  source: "builtin" | "user";
  builtin: boolean;
  enabled: boolean;
  path?: string | null;
  ui: {
    kind: "form" | "builtin";
    panel: string;
    run_mode: "preview_apply" | "run";
    mode_param: string;
    mode_inverted: boolean;
    apply_hint: string;
  };
  run: { max_concurrent: number; cancel: "immediate" | "cooperative"; undo: boolean };
  permissions: { network: boolean; writes_files: boolean; runs_programs: boolean };
  params: ModParam[];
}

export interface ModLoadError {
  path: string;
  message: string;
  id?: string | null;
}

export interface ModsResponse {
  mods: ModInfo[];
  errors: ModLoadError[];
  safe_mode: boolean;
  mods_dir: string;
}
