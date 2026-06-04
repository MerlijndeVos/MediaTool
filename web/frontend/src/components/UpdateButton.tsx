import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Info, Loader2, RefreshCw } from "lucide-react";
import {
  applyUpdate,
  checkForUpdates,
  fetchUpdateStatus,
  type UpdateApplyStatus,
  type UpdateCheck,
} from "@/api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { isDesktopApp } from "@/lib/desktop";

const CHECK_INTERVAL_MS = 60 * 60 * 1000;

function ReleaseNotes({ text }: { text: string }) {
  return (
    <div className="max-h-64 space-y-1.5 overflow-y-auto text-xs leading-relaxed text-muted-foreground">
      {text.split("\n").map((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) return null;

        if (trimmed.startsWith("### ")) {
          return (
            <p key={index} className="pt-1 font-semibold text-foreground">
              {trimmed.slice(4)}
            </p>
          );
        }
        if (trimmed.startsWith("## ")) {
          return (
            <p key={index} className="pt-1 font-semibold text-foreground">
              {trimmed.slice(3)}
            </p>
          );
        }
        if (trimmed.startsWith("# ")) {
          return (
            <p key={index} className="font-semibold text-foreground">
              {trimmed.slice(2)}
            </p>
          );
        }
        if (/^[-*]\s+/.test(trimmed)) {
          return (
            <p key={index} className="pl-3 before:mr-1.5 before:content-['•']">
              {trimmed.replace(/^[-*]\s+/, "")}
            </p>
          );
        }
        return <p key={index}>{trimmed}</p>;
      })}
    </div>
  );
}

function UpdateFeedback({
  checking,
  check,
  networkError,
}: {
  checking: boolean;
  check: UpdateCheck | null;
  networkError: string | null;
}) {
  const error = networkError ?? check?.error;
  const status = checking ? "Checking for updates…" : check?.status_message;

  if (!error && !status) return null;

  return (
    <span
      className={cn(
        "max-w-[14rem] text-xs leading-snug",
        error ? "text-red-600 dark:text-red-400" : "text-muted-foreground",
      )}
      title={error ?? status ?? undefined}
    >
      {error ?? status}
    </span>
  );
}

export function UpdateButton() {
  const [check, setCheck] = useState<UpdateCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [networkError, setNetworkError] = useState<string | null>(null);
  const [applyStatus, setApplyStatus] = useState<UpdateApplyStatus | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [whatsNewOpen, setWhatsNewOpen] = useState(false);
  const whatsNewRef = useRef<HTMLDivElement>(null);

  const runCheck = useCallback(async () => {
    setChecking(true);
    setNetworkError(null);
    try {
      setCheck(await checkForUpdates());
    } catch (err) {
      setCheck(null);
      setNetworkError(
        err instanceof Error ? err.message : "Could not reach the update server.",
      );
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    if (!isDesktopApp()) return;
    runCheck();
    const id = setInterval(runCheck, CHECK_INTERVAL_MS);
    return () => clearInterval(id);
  }, [runCheck]);

  const applying = applyStatus?.phase === "downloading" || applyStatus?.phase === "installing";

  useEffect(() => {
    if (!applying) return;
    const id = setInterval(async () => {
      try {
        setApplyStatus(await fetchUpdateStatus());
      } catch {
        /* ignore */
      }
    }, 500);
    return () => clearInterval(id);
  }, [applying]);

  useEffect(() => {
    if (!whatsNewOpen) return;

    const onPointerDown = (event: MouseEvent) => {
      if (!whatsNewRef.current?.contains(event.target as Node)) {
        setWhatsNewOpen(false);
      }
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setWhatsNewOpen(false);
    };

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [whatsNewOpen]);

  if (!isDesktopApp()) return null;

  const showUpdate =
    check?.update_available && check.can_install && check.latest_version;
  const releaseNotes = check?.release_notes?.trim();

  const versionTitle = check
    ? check.error
      ? `Media Tool v${check.current_version} — update check failed`
      : check.update_available
        ? `Media Tool v${check.current_version} — update available`
        : check.status_message
          ? `Media Tool v${check.current_version} — ${check.status_message}`
          : `Media Tool v${check.current_version}`
    : "Check for updates";

  const handleApply = async () => {
    setApplyError(null);
    setWhatsNewOpen(false);
    try {
      const result = await applyUpdate();
      if (!result.ok) {
        setApplyError(result.detail ?? "Could not start update.");
        return;
      }
      setApplyStatus(await fetchUpdateStatus());
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : "Could not start update.");
    }
  };

  return (
    <div className="flex max-w-[min(100%,28rem)] items-center gap-2">
      <UpdateFeedback checking={checking} check={check} networkError={networkError} />
      {applyError && (
        <span className="max-w-[14rem] truncate text-xs text-red-600 dark:text-red-400" title={applyError}>
          {applyError}
        </span>
      )}
      {applyStatus?.phase === "error" && applyStatus.error && (
        <span
          className="max-w-[14rem] truncate text-xs text-red-600 dark:text-red-400"
          title={applyStatus.error}
        >
          {applyStatus.error}
        </span>
      )}
      {showUpdate ? (
        <div ref={whatsNewRef} className="relative flex shrink-0 items-center gap-1">
          {releaseNotes && (
            <>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="gap-1 text-muted-foreground"
                disabled={applying}
                aria-expanded={whatsNewOpen}
                aria-haspopup="dialog"
                onClick={() => setWhatsNewOpen((open) => !open)}
              >
                <Info className="h-3.5 w-3.5" />
                What&apos;s new
              </Button>
              {whatsNewOpen && (
                <div
                  role="dialog"
                  aria-label={`What's new in v${check.latest_version}`}
                  className="absolute right-0 top-full z-50 mt-2 w-80 rounded-lg border bg-card p-3 text-card-foreground shadow-lg"
                >
                  <p className="mb-2 text-sm font-semibold">v{check.latest_version}</p>
                  <ReleaseNotes text={releaseNotes} />
                  {check.release_url && (
                    <a
                      href={check.release_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-3 inline-block text-xs text-primary hover:underline"
                    >
                      View full release notes
                    </a>
                  )}
                </div>
              )}
            </>
          )}
          <Button
            variant="default"
            size="sm"
            className="shrink-0 gap-1.5"
            disabled={applying}
            onClick={handleApply}
            title={releaseNotes ? "Download and install update" : undefined}
          >
            {applying ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                {applyStatus?.message || "Updating…"}
              </>
            ) : (
              <>
                <Download className="h-3.5 w-3.5" />
                Update to v{check.latest_version}
              </>
            )}
          </Button>
        </div>
      ) : (
        <Button
          variant="ghost"
          size="sm"
          className="shrink-0 gap-1.5 text-muted-foreground"
          disabled={checking}
          onClick={runCheck}
          title={versionTitle}
        >
          {checking ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          {check ? `v${check.current_version}` : "Updates"}
        </Button>
      )}
    </div>
  );
}
