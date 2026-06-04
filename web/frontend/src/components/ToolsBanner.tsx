import { AlertTriangle, ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchToolsStatus, type ToolsStatus } from "@/api/client";
import { Button } from "@/components/ui/button";

export function ToolsBanner() {
  const [status, setStatus] = useState<ToolsStatus | null>(null);

  useEffect(() => {
    fetchToolsStatus().then(setStatus).catch(() => setStatus(null));
    const id = setInterval(() => {
      fetchToolsStatus().then(setStatus).catch(() => undefined);
    }, 15000);
    return () => clearInterval(id);
  }, []);

  if (!status) return null;

  const warnings: string[] = [];
  if (!status.ffmpeg.available) {
    warnings.push("ffmpeg is not available yet. Restart the app or wait for the first-run download to finish.");
  }
  if (!status.mkvtoolnix.available && status.mkvtoolnix.message) {
    warnings.push(status.mkvtoolnix.message);
  }
  if (!warnings.length) return null;

  return (
    <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2">
      <div className="mx-auto flex max-w-6xl flex-wrap items-start gap-3 text-sm text-amber-950 dark:text-amber-100">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1 space-y-1">
          {warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
        {!status.mkvtoolnix.available && status.mkvtoolnix.install_url && (
          <Button variant="outline" size="sm" className="shrink-0" asChild>
            <a href={status.mkvtoolnix.install_url} target="_blank" rel="noreferrer">
              Get MKVToolNix
              <ExternalLink className="ml-1 h-3.5 w-3.5" />
            </a>
          </Button>
        )}
      </div>
    </div>
  );
}
