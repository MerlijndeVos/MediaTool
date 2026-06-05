import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Strip whitespace and surrounding quotes from a filesystem path. */
export function normalizeFilePath(path: string): string {
  return path.trim().replace(/^["']+|["']+$/g, "");
}

const VIDEO_EXTENSIONS = new Set([
  "dv", "avi", "divx", "flv", "m2ts", "m4v", "mkv", "mov", "mp4", "mpeg", "mpg", "mts", "ogm", "ts", "vob", "webm", "wmv",
]);

/** Lowercase extension without a dot, or empty when unknown. */
export function fileExtension(path: string): string {
  const normalized = normalizeFilePath(path);
  const match = normalized.match(/\.([^./\\]+)$/);
  if (!match) return "";
  return match[1].toLowerCase();
}

export function withFileExtension(path: string, ext: string): string {
  const normalized = normalizeFilePath(path);
  if (!normalized) return "";
  const format = ext.toLowerCase().replace(/^\./, "");
  const stem = normalized.replace(/\.[^./\\]+$/, "");
  return `${stem}.${format}`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 100 || unit === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unit]}`;
}

export function formatSpeed(bytesPerSec: number | null | undefined): string {
  if (bytesPerSec == null || bytesPerSec <= 0) return "—";
  return `${formatBytes(bytesPerSec)}/s`;
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0 || !Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return `${h}h ${rm}m`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export { VIDEO_EXTENSIONS };
