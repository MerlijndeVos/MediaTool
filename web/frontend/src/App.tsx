import { useEffect, useMemo, useState } from "react";
import { Film, Moon, Sun, Wifi, WifiOff } from "lucide-react";
import { checkHealth } from "@/api/client";
import { LogDrawer } from "@/components/LogDrawer";
import { ToolsBanner } from "@/components/ToolsBanner";
import { ToolPanel } from "@/components/ToolPanel";
import { UpdateButton } from "@/components/UpdateButton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  PRIMARY_TOOLS,
  SECONDARY_TOOLS,
  TOOL_LABELS,
  type ToolId,
} from "@/lib/types";
import { useJobRunner } from "@/hooks/useJobRunner";

export default function App() {
  const [tool, setTool] = useState<ToolId>("convert");
  const [logOpen, setLogOpen] = useState(true);
  const [dark, setDark] = useState(() =>
    typeof window !== "undefined"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
      : false,
  );
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [running, setRunning] = useState(false);
  const { jobs, logs, startJob, cancel, clearLogs, dismissFinishedDownloads } = useJobRunner();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  useEffect(() => {
    const tick = () => checkHealth().then(setApiOk);
    tick();
    const id = setInterval(tick, 5000);
    return () => clearInterval(id);
  }, []);

  const activeJob = useMemo(
    () =>
      tool === "download"
        ? undefined
        : jobs.find((j) => j.command === tool && (j.status === "running" || j.status === "queued")),
    [jobs, tool],
  );

  const downloadJobs = useMemo(
    () => jobs.filter((j) => j.command === "download"),
    [jobs],
  );

  const handleRun = async (params: Record<string, unknown>) => {
    setLogOpen(true);
    if (tool === "download") {
      await startJob(tool, params, true, {
        downloadMeta: {
          url: String(params.url),
          format: String(params.format ?? "mp4"),
          output: String(params.output),
        },
      });
      return;
    }
    setRunning(true);
    try {
      await startJob(tool, params);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="min-h-screen pb-16">
      <ToolsBanner />
      <header className="sticky top-0 z-30 border-b bg-card/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Film className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-base font-semibold leading-tight">Media Tool</h1>
              <p className="text-xs text-muted-foreground">Local processing only</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <UpdateButton />
            <span
              className={cn(
                "flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium",
                apiOk === true && "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
                apiOk === false && "bg-red-500/15 text-red-700 dark:text-red-400",
                apiOk === null && "bg-muted text-muted-foreground",
              )}
            >
              {apiOk ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
              {apiOk === true ? "API connected" : apiOk === false ? "API offline" : "Checking…"}
            </span>
            <Button variant="ghost" size="icon" onClick={() => setDark((d) => !d)} aria-label="Toggle theme">
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-6 lg:grid-cols-[220px_1fr]">
        <aside className="space-y-6">
          <nav className="space-y-1">
            <p className="px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Main
            </p>
            {PRIMARY_TOOLS.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => setTool(id)}
                className={cn(
                  "w-full rounded-md px-3 py-2 text-left text-sm font-medium transition-colors",
                  tool === id
                    ? "bg-primary text-primary-foreground"
                    : "text-foreground hover:bg-accent",
                )}
              >
                {TOOL_LABELS[id]}
              </button>
            ))}
          </nav>
          <nav className="space-y-1">
            <p className="px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              More tools
            </p>
            {SECONDARY_TOOLS.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => setTool(id)}
                className={cn(
                  "w-full rounded-md px-3 py-2 text-left text-sm transition-colors",
                  tool === id
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                {TOOL_LABELS[id]}
              </button>
            ))}
          </nav>
        </aside>

        <main>
          {apiOk === false && (
            <div className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
              Start the API server: <code className="rounded bg-muted px-1">python -m web</code>
              {import.meta.env.DEV && (
                <> — dev UI proxies <code className="rounded bg-muted px-1">/api</code> to port 8765</>
              )}
            </div>
          )}
          <ToolPanel
            tool={tool}
            onRun={handleRun}
            running={running}
            activeJob={activeJob}
            downloadJobs={downloadJobs}
            onCancelDownload={cancel}
            onDismissFinishedDownloads={dismissFinishedDownloads}
          />
        </main>
      </div>

      <LogDrawer open={logOpen} onToggle={() => setLogOpen((o) => !o)} logs={logs} onClear={clearLogs} />
    </div>
  );
}
