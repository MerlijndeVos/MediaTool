import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, Download, House, Palette, Puzzle, ScrollText, Wifi, WifiOff } from "lucide-react";
import { checkHealth, fetchSettings } from "@/api/client";
import { AppearancePanel } from "@/components/AppearancePanel";
import { HomePanel } from "@/components/HomePanel";
import { LogDrawer } from "@/components/LogDrawer";
import { ToolsBanner } from "@/components/ToolsBanner";
import { LoggingPanel } from "@/components/LoggingPanel";
import { ModsPanel } from "@/components/ModsPanel";
import { OpenAiSettingsPanel } from "@/components/OpenAiSettingsPanel";
import { ToolPanel } from "@/components/ToolPanel";
import { UpdateModal } from "@/components/UpdateModal";
import { UpdatesPanel } from "@/components/UpdatesPanel";
import { cn } from "@/lib/utils";
import { isDesktopApp } from "@/lib/desktop";
import { useMods } from "@/hooks/useMods";
import { useUpdates } from "@/hooks/useUpdates";
import type { DownloadJobMeta, ToolId } from "@/lib/types";
import { useJobRunner } from "@/hooks/useJobRunner";

type AppView = "home" | "tools" | "logs" | "openai" | "updates" | "appearance" | "mods";

export default function App() {
  const updates = useUpdates();
  const mods = useMods();
  const desktop = isDesktopApp();
  const [view, setView] = useState<AppView>("home");
  const [tool, setTool] = useState<ToolId>("convert");
  const [fileLogging, setFileLogging] = useState(true);
  const [logOpen, setLogOpen] = useState(true);
  const [logHeight, setLogHeight] = useState(256);
  const [dark, setDark] = useState(() =>
    typeof window !== "undefined"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
      : false,
  );
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [running, setRunning] = useState(false);
  const logClosedByUser = useRef(false);
  const {
    jobs,
    logs,
    startJob,
    startJobs,
    cancel,
    clearLogs,
    dismissFinishedDownloads,
    undoRename,
    undoing,
  } = useJobRunner();

  const undoableRenameJobs = useMemo(
    () =>
      jobs.filter(
        (j) =>
          !j.undo_of &&
          j.status === "completed" &&
          j.undo_available &&
          !j.undo_used,
      ),
    [jobs],
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  useEffect(() => {
    const tick = () => checkHealth().then(setApiOk);
    tick();
    const id = setInterval(tick, 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    fetchSettings()
      .then((s) => setFileLogging(s.file_logging))
      .catch(() => undefined);
  }, []);

  const activeJob = useMemo(() => {
    if (tool === "download") return undefined;
    const running = jobs.find(
      (j) => j.command === tool && (j.status === "running" || j.status === "queued"),
    );
    if (running) return running;
    if (tool === "subtitle_translate" || tool === "subtitle_cleanup") {
      return jobs.find((j) => j.command === tool && j.status === "completed");
    }
    return undefined;
  }, [jobs, tool]);

  const downloadJobs = useMemo(
    () => jobs.filter((j) => j.command === "download"),
    [jobs],
  );

  const handleQueueDownloads = async (
    items: Array<{ params: Record<string, unknown>; downloadMeta: DownloadJobMeta }>,
  ) => {
    await startJobs(
      "download",
      items.map((item) => ({
        params: item.params,
        downloadMeta: item.downloadMeta,
      })),
      fileLogging,
    );
  };

  const handleRun = async (params: Record<string, unknown>) => {
    if (tool !== "download" && !logClosedByUser.current) {
      setLogOpen(true);
    }
    if (tool === "download") {
      await startJob(tool, params, fileLogging, {
        downloadMeta: {
          url: String(params.url),
          format: String(params.format ?? "mp4"),
          output: String(params.output),
          displayName: params.output_name ? String(params.output_name) : undefined,
        },
      });
      return;
    }
    setRunning(true);
    try {
      await startJob(tool, params, fileLogging);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="min-h-screen" style={{ paddingBottom: logHeight }}>
      <ToolsBanner />
      <header className="sticky top-0 z-30 border-b bg-card/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <button
            type="button"
            onClick={() => setView("home")}
            className="flex items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Toolbox home"
          >
            <img
              src="/app/favicon.svg"
              alt=""
              className="size-8 shrink-0 rounded-[9px]"
              width={32}
              height={32}
            />
            <h1 className="text-base font-semibold leading-none">Toolbox</h1>
          </button>
          <div className="flex items-center gap-2">
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
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-6 lg:grid-cols-[220px_1fr]">
        <aside className="space-y-6">
          <button
            type="button"
            onClick={() => setView("home")}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm font-medium transition-colors",
              view === "home"
                ? "bg-primary text-primary-foreground"
                : "text-foreground hover:bg-accent",
            )}
          >
            <House className="h-4 w-4" />
            Home
          </button>
          {mods.groups.map((group) => {
            const muted = group.name.toLowerCase() === "experimental";
            return (
              <nav key={group.name} className="space-y-1">
                <p className="px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {group.name}
                </p>
                {group.mods.map((mod) => (
                  <button
                    key={mod.id}
                    type="button"
                    onClick={() => {
                      setView("tools");
                      setTool(mod.id);
                    }}
                    className={cn(
                      "w-full rounded-md px-3 py-2 text-left text-sm transition-colors",
                      !muted && "font-medium",
                      view === "tools" && tool === mod.id
                        ? "bg-primary text-primary-foreground"
                        : muted
                          ? "text-muted-foreground hover:bg-accent hover:text-foreground"
                          : "text-foreground hover:bg-accent",
                    )}
                  >
                    {mod.name}
                  </button>
                ))}
              </nav>
            );
          })}
          <nav className="space-y-1 border-t border-border/60 pt-4">
            <p className="px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Settings
            </p>
            <button
              type="button"
              onClick={() => setView("logs")}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                view === "logs"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <ScrollText className="h-4 w-4" />
              Logs
            </button>
            <button
              type="button"
              onClick={() => setView("openai")}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                view === "openai"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <Bot className="h-4 w-4" />
              OpenAI
            </button>
            {desktop && (
              <button
                type="button"
                onClick={() => setView("updates")}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                  view === "updates"
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                <Download className="h-4 w-4" />
                Updates
                {updates.showUpdate && (
                  <span
                    className={cn(
                      "ml-auto rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                      view === "updates"
                        ? "bg-primary-foreground/20 text-primary-foreground"
                        : "bg-primary/15 text-primary",
                    )}
                  >
                    New
                  </span>
                )}
              </button>
            )}
            <button
              type="button"
              onClick={() => setView("mods")}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                view === "mods"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <Puzzle className="h-4 w-4" />
              Mods
            </button>
            <button
              type="button"
              onClick={() => setView("appearance")}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                view === "appearance"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <Palette className="h-4 w-4" />
              Appearance
            </button>
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
          {view === "home" ? (
            <HomePanel
              groups={mods.groups}
              desktop={desktop}
              updateAvailable={updates.showUpdate}
              onOpenTool={(id) => {
                setTool(id);
                setView("tools");
              }}
              onOpenSettings={setView}
            />
          ) : view === "logs" ? (
            <LoggingPanel onFileLoggingChange={setFileLogging} />
          ) : view === "openai" ? (
            <OpenAiSettingsPanel />
          ) : view === "updates" ? (
            <UpdatesPanel {...updates} />
          ) : view === "appearance" ? (
            <AppearancePanel dark={dark} onDarkChange={setDark} />
          ) : view === "mods" ? (
            <ModsPanel mods={mods} />
          ) : (
            <ToolPanel
              tool={tool}
              mods={mods.enabledMods}
              onRun={handleRun}
              onQueueDownloads={handleQueueDownloads}
              running={running}
              activeJob={activeJob}
              downloadJobs={downloadJobs}
              onCancelDownload={cancel}
              onDismissFinishedDownloads={dismissFinishedDownloads}
            />
          )}
        </main>
      </div>

      {desktop && updates.showUpdate && updates.check?.latest_version && (
        <UpdateModal
          open={updates.modalOpen}
          currentVersion={updates.check.current_version}
          latestVersion={updates.check.latest_version}
          releaseNotes={updates.check.release_notes}
          releaseUrl={updates.check.release_url}
          applying={updates.applying}
          applyStatus={updates.applyStatus}
          onSkip={updates.handleSkip}
          onUpdate={updates.handleApply}
        />
      )}

      <LogDrawer
        open={logOpen}
        onToggle={() => {
          setLogOpen((open) => {
            const next = !open;
            logClosedByUser.current = !next;
            return next;
          });
        }}
        logs={logs}
        onClear={clearLogs}
        onHeightChange={setLogHeight}
        undoableJobs={undoableRenameJobs}
        onUndoRename={async (jobId) => {
          if (!logClosedByUser.current) setLogOpen(true);
          await undoRename(jobId);
        }}
        undoing={undoing}
      />
    </div>
  );
}
