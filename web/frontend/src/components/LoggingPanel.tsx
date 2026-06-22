import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ExternalLink, FolderOpen, Loader2, RefreshCw, Trash2 } from "lucide-react";
import {
  clearLogFiles,
  fetchSettings,
  openLogFile,
  openLogFolder,
  updateSettings,
  type AppSettings,
} from "@/api/client";
import { CheckField } from "@/components/fields";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatBytes } from "@/lib/utils";

interface LoggingPanelProps {
  onFileLoggingChange?: (enabled: boolean) => void;
}

export function LoggingPanel({ onFileLoggingChange }: LoggingPanelProps) {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await fetchSettings();
      setSettings(data);
      onFileLoggingChange?.(data.file_logging);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [onFileLoggingChange]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleFileLoggingChange = async (enabled: boolean) => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const data = await updateSettings({ file_logging: enabled });
      setSettings(data);
      onFileLoggingChange?.(data.file_logging);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleClearLogs = async () => {
    setClearing(true);
    setError(null);
    try {
      const result = await clearLogFiles();
      setSettings((prev) => (prev ? { ...prev, logs: result.logs } : prev));
      setConfirmClear(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setClearing(false);
    }
  };

  const handleOpenFolder = async () => {
    setError(null);
    setOpening("folder");
    try {
      await openLogFolder();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOpening(null);
    }
  };

  const handleOpenFile = async (name: string) => {
    setError(null);
    setOpening(name);
    try {
      await openLogFile(name);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOpening(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading logs…
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
        {error ?? "Could not load logs."}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Disk logging</CardTitle>
          <CardDescription>
            Operation logs are stored in the app data folder, not next to your media files.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <CheckField
            label="Save logs to disk"
            checked={settings.file_logging}
            onChange={handleFileLoggingChange}
            disabled={saving}
            hint="When off, logs appear in the bottom panel only."
            tooltip="Log files are written under your local Media Tool data directory."
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
          <div className="space-y-1.5">
            <CardTitle>Stored logs</CardTitle>
            <CardDescription>
              Total size:{" "}
              <span className="font-medium text-foreground">{formatBytes(settings.logs.total_bytes)}</span>
              {settings.logs.file_count > 0 && (
                <> · {settings.logs.file_count} file{settings.logs.file_count === 1 ? "" : "s"}</>
              )}
            </CardDescription>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => void load()} disabled={clearing}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="min-w-0 flex-1 break-all text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Location:</span> {settings.logs.path}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleOpenFolder()}
              disabled={opening != null}
            >
              {opening === "folder" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <FolderOpen className="h-4 w-4" />
              )}
              Open folder
            </Button>
          </div>

          {settings.logs.files.length > 0 ? (
            <ul className="divide-y rounded-md border text-sm">
              {settings.logs.files.map((file) => (
                <li key={file.name}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors hover:bg-muted/60 disabled:opacity-60"
                    onClick={() => void handleOpenFile(file.name)}
                    disabled={opening != null}
                    title={`Open ${file.name}`}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      {opening === file.name ? (
                        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
                      ) : (
                        <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      )}
                      <span className="truncate font-mono text-xs">{file.name}</span>
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {formatBytes(file.size_bytes)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No log files yet.</p>
          )}

          {confirmClear ? (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
              <div className="flex gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700 dark:text-amber-300" />
                <div className="space-y-3">
                  <p className="text-sm">
                    Delete all {settings.logs.file_count} log file
                    {settings.logs.file_count === 1 ? "" : "s"} ({formatBytes(settings.logs.total_bytes)})? This
                    cannot be undone.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      onClick={() => void handleClearLogs()}
                      disabled={clearing}
                    >
                      {clearing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                      Delete all logs
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setConfirmClear(false)}
                      disabled={clearing}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <Button
              type="button"
              variant="outline"
              onClick={() => setConfirmClear(true)}
              disabled={settings.logs.file_count === 0 || clearing}
            >
              <Trash2 className="h-4 w-4" />
              Clear all logs
            </Button>
          )}
        </CardContent>
      </Card>

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}
    </div>
  );
}
