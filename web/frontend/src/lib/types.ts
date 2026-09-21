import type { ModAccent } from "@/lib/groups";

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
  /** Set when the job renamed the folder the user had selected. */
  renamed_root?: { from: string; to: string } | null;
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

export type ResultLevel = "info" | "success" | "warning" | "error";

/** What a mod chose to show after a run (`ctx.result(...)`), as plain data. Never HTML. */
export type ModResult =
  | { view: "table"; title: string; columns: string[]; rows: (string | number)[][]; truncated: boolean }
  | { view: "counters"; title: string; items: { label: string; value: string }[] }
  | { view: "files"; title: string; files: { path: string; label?: string }[]; truncated: boolean }
  | { view: "markdown"; title: string; text: string }
  | { view: "image"; title: string; src: string; alt: string }
  | { view: "message"; title: string; text: string; level: ResultLevel };

export interface ActiveJob extends JobSummary {
  /** What the mod showed after the run; grows while the job runs. */
  results?: ModResult[];
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
  | "json"
  | "multichoice"
  | "color"
  | "date";

export type ModType = "tool" | "theme";

/** `show_if`: show a field or section only while another param has a certain value. */
export interface ShowIf {
  param: string;
  op: "equals" | "not_equals" | "in" | "truthy" | "falsy";
  value?: unknown;
}

export interface ModSection {
  id: string;
  title: string;
  /** Markdown-lite text shown under the title. */
  text: string;
  show_if: ShowIf | null;
}

export interface ModAction {
  name: string;
  label: string;
  help: string;
  /** Which params the action receives; null = all of them. */
  params: string[] | null;
}

/** A theme as the API sends it: what it sets, and every token resolved against the default. */
export interface ThemeData {
  light: Record<string, string>;
  dark: Record<string, string>;
  radius: string | null;
  font: string | null;
  resolved: {
    light: Record<string, string>;
    dark: Record<string, string>;
    radius: string;
    font_stack: string;
  };
  swatches: { light: string[]; dark: string[] };
  warnings: string[];
}

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
  /** The section this field sits in; empty = above all sections. */
  section: string;
  show_if: ShowIf | null;
  widget: "default" | "slider";
  step?: number | null;
}

export interface ModInfo {
  id: string;
  name: string;
  description: string;
  version: string;
  author: string;
  type: ModType;
  group: string;
  /** Tile colour: a category or status name, or empty for the category's own. */
  accent: ModAccent;
  order: number;
  icon: string;
  source: "builtin" | "user";
  builtin: boolean;
  enabled: boolean;
  path?: string | null;
  /** Where an installed mod came from; null for built-in features and mods that were just dropped in. */
  install?: ModInstallMeta | null;
  ui: {
    kind: "form" | "builtin";
    layout: "sections" | "tabs";
    panel: string;
    run_mode: "preview_apply" | "run";
    mode_param: string;
    mode_inverted: boolean;
    apply_hint: string;
  };
  run: { max_concurrent: number; cancel: "immediate" | "cooperative"; undo: boolean };
  permissions: { network: boolean; writes_files: boolean; runs_programs: boolean };
  params: ModParam[];
  sections: ModSection[];
  actions: ModAction[];
  /** Set for theme mods. */
  theme: ThemeData | null;
}

export interface ModLoadError {
  path: string;
  message: string;
  id?: string | null;
}

export interface ModNotice {
  id: string;
  message: string;
}

export interface ModsResponse {
  mods: ModInfo[];
  errors: ModLoadError[];
  /** Things worth a look that do not stop a mod from loading (a category that looks like another). */
  notices: ModNotice[];
  /** The built-in categories, in on-screen order, with what belongs in each. */
  groups: { name: string; description: string }[];
  safe_mode: boolean;
  mods_dir: string;
}

export interface ModInstallMeta {
  type: "git" | "folder" | "zip" | "file";
  /** git installs: the repository, the ref the user asked for, the pinned commit and the folder inside it. */
  url?: string;
  ref?: string;
  commit?: string;
  subdir?: string;
  /** folder, zip and file installs: where it was copied from. */
  path?: string;
  version?: string;
  installed_at?: string;
}

export interface ModSourceFile {
  path: string;
  size: number;
  /** null for binary files (and for text beyond the size shown here). */
  text: string | null;
  truncated: boolean;
}

/** Where a tool would appear once installed. */
export interface ModPlacement {
  name: string;
  new_section: boolean;
  near_miss: string | null;
}

export interface ModInstallPreview {
  token: string;
  manifest: Omit<ModInfo, "source" | "builtin" | "enabled" | "path" | "install">;
  /** null for themes. */
  placement: ModPlacement | null;
  source: ModInstallMeta;
  files: ModSourceFile[];
  warnings: string[];
  /** Set when this replaces an installed version (an update). */
  replaces: { version: string; commit: string } | null;
  changes: { path: string; status: "added" | "removed" | "changed" }[] | null;
  compare_url: string | null;
}

export interface ModSourceResponse {
  id: string;
  files: ModSourceFile[];
  warnings: string[];
}

export interface ModUpdateStatus {
  supported: boolean;
  reason?: string;
  available?: boolean;
  current?: string;
  latest?: string;
  ref?: string;
  compare_url?: string | null;
}

export interface MarketEntry {
  id: string;
  name: string;
  description: string;
  author: string;
  version: string;
  api_version: number;
  type: ModType;
  /** The section a tool appears in, as the listing states it (empty when it does not say). */
  group: string;
  /** Colours of a theme, so it can be judged without installing it. */
  swatches: string[];
  repo: string;
  path: string;
  commit: string;
  tags: string[];
  license: string;
  homepage: string;
  permissions: { network: boolean; writes_files: boolean; runs_programs: boolean } | null;
}

export interface MarketResponse {
  url: string;
  mods: MarketEntry[];
  problems: string[];
  error: string | null;
}

export interface ModPrompts {
  build: string;
  review: string;
  theme: string;
}
