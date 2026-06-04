import type { CommandName, JobCreateResponse, JobSummary } from "@/lib/types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

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
    throw new Error(text || `HTTP ${res.status}`);
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
  authenticated?: boolean;
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
  mkvtoolnix: {
    available: boolean;
    install_url?: string;
    message?: string | null;
  };
}

export function fetchToolsStatus(): Promise<ToolsStatus> {
  return request<ToolsStatus>("/api/tools");
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

export function listJobs(): Promise<JobSummary[]> {
  return request<JobSummary[]>("/api/jobs");
}

export function getJob(id: string): Promise<JobSummary> {
  return request<JobSummary>(`/api/jobs/${id}`);
}

export function cancelJob(id: string): Promise<void> {
  return request(`/api/jobs/${id}/cancel`, { method: "POST" }).then(() => undefined);
}

export function jobEventsUrl(id: string): string {
  return `${API_BASE}/api/jobs/${id}/events`;
}
