import { AlertTriangle, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  fetchToolsStatus,
  retryToolsBootstrap,
  type ToolsStatus,
} from "@/api/client";
import { Button } from "@/components/ui/button";

const ACTIVE_PHASES = new Set(["checking", "downloading", "verifying"]);

export function ToolsBanner() {
  const [status, setStatus] = useState<ToolsStatus | null>(null);

  const refresh = useCallback(() => {
    fetchToolsStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    refresh();
    const phase = status?.bootstrap?.phase;
    const intervalMs = phase && ACTIVE_PHASES.has(phase) ? 2000 : 8000;
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, status?.bootstrap?.phase]);

  if (!status) return null;
  if (status.ffmpeg.available) return null;

  const phase = status.bootstrap?.phase ?? "idle";
  const message = status.bootstrap?.message;
  const error = status.bootstrap?.error;
  const busy = ACTIVE_PHASES.has(phase);

  return (
    <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2">
      <div className="mx-auto flex max-w-6xl flex-wrap items-start gap-3 text-sm text-amber-950 dark:text-amber-100">
        {busy ? (
          <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin" />
        ) : (
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        )}
        <div className="min-w-0 flex-1 space-y-1">
          {busy && (
            <p>
              {message ||
                "Setting up ffmpeg (first run, one-time download). Keep the app open…"}
            </p>
          )}
          {phase === "failed" && (
            <>
              <p>{message || "ffmpeg setup failed."}</p>
              {error && <p className="text-xs opacity-90">{error}</p>}
            </>
          )}
          {!busy && phase !== "failed" && (
            <p>
              ffmpeg is not available yet. The app will download it automatically on
              first run when online.
            </p>
          )}
        </div>
        {phase === "failed" && (
          <Button
            variant="outline"
            size="sm"
            className="shrink-0"
            onClick={() => retryToolsBootstrap().then(setStatus).catch(() => undefined)}
          >
            Retry
          </Button>
        )}
      </div>
    </div>
  );
}
