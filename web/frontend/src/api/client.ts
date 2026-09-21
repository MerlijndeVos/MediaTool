import type {
  CommandName,
  DownloadProbeResult,
  JobCreateResponse,
  JobSummary,
  JobUndoResponse,
  ModsResponse,
} from "@/lib/types";
import type { RenameMode, RenameProfile } from "@/lib/renameProfiles";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

function parseApiError(text: string, status: number): string {
  try {
    const body = JSON.parse(text) as { detail?: string | Array<{ msg?: string }> };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      const msg = body.detail.map((d) => d.msg).filter(Boolean).join("; ");
      if (msg) return msg;
    }
  } catch {
    /* not JSON */
  }
  if (status === 404) {
    return (
      "API endpoint not found. An older server may still be running on port 8765 " +
      "(stop it with: netstat -ano | findstr :8765, then taskkill /PID <pid> /F), " +
      "then restart with: python -m web"
    );
  }
  return text.trim() || `HTTP ${status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseApiError(text, res.status));
  }
  return res.json() as Promise<T>;
}

export async function checkHealth(): Promise<boolean> {
  try {
    await request<{ status: string; version: string }>("/api/health");
    return true;
  } catch {
    return false;
  }
}

export interface UpdateCheck {
  current_version: string;
  latest_version?: string | null;
  update_available: boolean;
  can_install: boolean;
  download_url?: string | null;
  asset_name?: string | null;
  release_url?: string | null;
  release_notes?: string | null;
  error?: string | null;
  status_message?: string | null;
}

export interface UpdateApplyStatus {
  phase: "idle" | "downloading" | "installing" | "error";
  progress: number;
  message: string;
  error?: string | null;
}

export function checkForUpdates(): Promise<UpdateCheck> {
  return request<UpdateCheck>("/api/updates/check");
}

export function applyUpdate(): Promise<{ ok: boolean; detail?: string | null }> {
  return request("/api/updates/apply", { method: "POST" });
}

export function fetchUpdateStatus(): Promise<UpdateApplyStatus> {
  return request<UpdateApplyStatus>("/api/updates/status");
}

export interface ToolsStatus {
  ffmpeg: {
    available: boolean;
    ffmpeg_path?: string | null;
    ffprobe_path?: string | null;
    source?: string;
  };
  bootstrap?: {
    phase: "idle" | "checking" | "downloading" | "verifying" | "ready" | "failed";
    message?: string;
    error?: string | null;
  };
}

export function fetchToolsStatus(): Promise<ToolsStatus> {
  return request<ToolsStatus>("/api/tools");
}

export function retryToolsBootstrap(): Promise<ToolsStatus> {
  return request<ToolsStatus>("/api/tools/bootstrap", { method: "POST" });
}

export function probeDownloadUrl(params: {
  url: string;
  format: string;
  video_quality: string;
  audio_bitrate: number;
}): Promise<DownloadProbeResult> {
  return request<DownloadProbeResult>("/api/download/probe", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function createJob(
  command: CommandName,
  params: Record<string, unknown>,
  fileLogging = true,
): Promise<JobCreateResponse> {
  return request<JobCreateResponse>("/api/jobs", {
    method: "POST",
    body: JSON.stringify({ command, params, file_logging: fileLogging }),
  });
}

export function fetchMods(): Promise<ModsResponse> {
  return request<ModsResponse>("/api/mods");
}

export function reloadMods(): Promise<ModsResponse> {
  return request<ModsResponse>("/api/mods/reload", { method: "POST" });
}

export function setModEnabled(id: string, enabled: boolean): Promise<ModsResponse> {
  return request<ModsResponse>(`/api/mods/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
}

export function openModsFolder(): Promise<{ ok: boolean }> {
  return request("/api/mods/open-folder", { method: "POST" });
}

export function listJobs(): Promise<JobSummary[]> {
  return request<JobSummary[]>("/api/jobs");
}

export function getJob(id: string): Promise<JobSummary> {
  return request<JobSummary>(`/api/jobs/${id}`);
}

export function cancelJob(id: string): Promise<void> {
  return request(`/api/jobs/${id}/cancel`, { method: "POST" }).then(() => undefined);
}

export function undoRenameJob(sourceJobId: string): Promise<JobUndoResponse> {
  return request<JobUndoResponse>(`/api/jobs/${sourceJobId}/undo`, { method: "POST" });
}

export function jobEventsUrl(id: string): string {
  return `${API_BASE}/api/jobs/${id}/events`;
}

export interface LogFileInfo {
  name: string;
  size_bytes: number;
  modified_at: string;
}

export interface LogsStats {
  path: string;
  total_bytes: number;
  file_count: number;
  files: LogFileInfo[];
}

export type AiProviderId = "openai" | "openai_compatible" | "anthropic" | "gemini";

export interface AiProviderSettings {
  api_key_set: boolean;
  /** The key comes from an environment variable rather than the saved settings. */
  api_key_from_env: boolean;
  /** Effective model id (the saved one, or the provider default). */
  model: string;
  default_model: string;
  base_url: string;
}

export interface AiSettings {
  provider: AiProviderId;
  providers: Record<AiProviderId, AiProviderSettings>;
}

export interface AppSettings {
  file_logging: boolean;
  ai: AiSettings;
  logs: LogsStats;
}

/** Omitted fields are kept; an empty string clears the field. */
export interface AiProviderUpdate {
  api_key?: string;
  model?: string;
  base_url?: string;
}

export function fetchSettings(): Promise<AppSettings> {
  return request<AppSettings>("/api/settings");
}

export function updateSettings(patch: {
  file_logging?: boolean;
  ai?: {
    provider?: AiProviderId;
    providers?: Partial<Record<AiProviderId, AiProviderUpdate>>;
  };
}): Promise<AppSettings> {
  return request<AppSettings>("/api/settings", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export interface AiTestResult {
  ok: boolean;
  message: string;
}

/** Try a provider with the form values; blank fields fall back to the saved ones. */
export function testAiConnection(
  body: AiProviderUpdate & { provider: AiProviderId },
): Promise<AiTestResult> {
  return request<AiTestResult>("/api/ai/test", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface SubtitleLanguage {
  code: string;
  label: string;
}

export interface SubtitleJunkItem {
  id: string;
  file: string;
  cue_index: number;
  line_index: number;
  text: string;
  reason: string;
  reason_label: string;
}

export interface SubtitleScanJunkResult {
  items: SubtitleJunkItem[];
  detected_source_lang?: string | null;
}

export function fetchSubtitleLanguages(): Promise<{ languages: SubtitleLanguage[] }> {
  return request("/api/subtitles/languages");
}

export function scanSubtitleJunk(input: string): Promise<SubtitleScanJunkResult> {
  return request<SubtitleScanJunkResult>("/api/subtitles/scan-junk", {
    method: "POST",
    body: JSON.stringify({ input }),
  });
}

export function clearLogFiles(): Promise<{ deleted_count: number; logs: LogsStats }> {
  return request("/api/settings/logs", { method: "DELETE" });
}

export interface LogChunk {
  name: string;
  size_bytes: number;
  /** Byte offset where this chunk starts; pass it as `end` to get the lines before it. */
  start: number;
  end: number;
  has_earlier: boolean;
  lines: string[];
}

/** Last `lines` lines of a stored log, or the lines before byte offset `end`. */
export function fetchLogChunk(name: string, opts: { end?: number; lines?: number } = {}): Promise<LogChunk> {
  const params = new URLSearchParams();
  if (opts.end != null) params.set("end", String(opts.end));
  if (opts.lines != null) params.set("lines", String(opts.lines));
  const query = params.toString();
  return request<LogChunk>(`/api/settings/logs/${encodeURIComponent(name)}${query ? `?${query}` : ""}`);
}

export function openLogFolder(): Promise<{ ok: boolean }> {
  return request("/api/settings/logs/open-folder", { method: "POST" });
}

export function openLogFile(name: string): Promise<{ ok: boolean }> {
  return request("/api/settings/logs/open-file", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

// ---------------------------------------------------------------------------
// Rename format profiles
// ---------------------------------------------------------------------------

export interface RenameTestResult {
  sample: string;
  result: string | null;
  note: string | null;
}

export interface RenameGenerateResult {
  profile: RenameProfile;
  verification: { before: string; expected: string; actual: string | null; ok: boolean }[];
  all_ok: boolean;
  attempts: number;
  model: string;
}

export function fetchRenameProfiles(): Promise<{ profiles: RenameProfile[] }> {
  return request<{ profiles: RenameProfile[] }>("/api/rename/profiles");
}

export function saveRenameProfile(profile: RenameProfile): Promise<RenameProfile> {
  return request<RenameProfile>("/api/rename/profiles", {
    method: "POST",
    body: JSON.stringify({ profile }),
  });
}

export function deleteRenameProfile(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/rename/profiles/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function testRenameProfile(
  profile: RenameProfile,
  mode: RenameMode,
  samples: string[],
): Promise<{ results: RenameTestResult[] }> {
  return request<{ results: RenameTestResult[] }>("/api/rename/profiles/test", {
    method: "POST",
    body: JSON.stringify({ profile, mode, samples }),
  });
}

export function generateRenameProfile(
  mode: RenameMode,
  examples: { before: string; after: string }[],
): Promise<RenameGenerateResult> {
  return request<RenameGenerateResult>("/api/rename/profiles/generate", {
    method: "POST",
    body: JSON.stringify({ mode, examples }),
  });
}
