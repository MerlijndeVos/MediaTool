import { useCallback, useEffect, useState } from "react";
import { Download, Loader2, RefreshCw } from "lucide-react";
import {
  applyUpdate,
  checkForUpdates,
  fetchUpdateStatus,
  type UpdateApplyStatus,
  type UpdateCheck,
} from "@/api/client";
import { UpdateModal } from "@/components/UpdateModal";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { isDesktopApp } from "@/lib/desktop";
import { isNewerVersionAvailable } from "@/lib/version";

const CHECK_INTERVAL_MS = 60 * 60 * 1000;
const SKIPPED_UPDATE_KEY = "media-tool-skipped-update";

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
  const [modalOpen, setModalOpen] = useState(false);

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
  const showUpdate = Boolean(
    check &&
      check.can_install &&
      check.latest_version &&
      isNewerVersionAvailable(check.current_version, check.latest_version, check.update_available),
  );

  useEffect(() => {
    if (!showUpdate || !check?.latest_version || applying) return;
    const skipped = localStorage.getItem(SKIPPED_UPDATE_KEY);
    if (skipped !== check.latest_version) {
      setModalOpen(true);
    }
  }, [showUpdate, check?.latest_version, applying]);

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

  const handleApply = async () => {
    setApplyError(null);
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

  const handleSkip = () => {
    if (check?.latest_version) {
      localStorage.setItem(SKIPPED_UPDATE_KEY, check.latest_version);
    }
    setModalOpen(false);
  };

  if (!isDesktopApp()) return null;

  const latestVersion = check?.latest_version;
  const versionTitle = check
    ? check.error
      ? `Media Tool v${check.current_version} — update check failed`
      : check.update_available
        ? `Media Tool v${check.current_version} — update available`
        : check.status_message
          ? `Media Tool v${check.current_version} — ${check.status_message}`
          : `Media Tool v${check.current_version}`
    : "Check for updates";

  return (
    <>
      {showUpdate && check?.latest_version && (
        <UpdateModal
          open={modalOpen}
          currentVersion={check.current_version}
          latestVersion={check.latest_version}
          releaseNotes={check.release_notes}
          releaseUrl={check.release_url}
          applying={applying}
          applyMessage={applyStatus?.message}
          onSkip={handleSkip}
          onUpdate={handleApply}
        />
      )}

      <div className="flex max-w-[min(100%,28rem)] items-center gap-2">
        <UpdateFeedback checking={checking} check={check} networkError={networkError} />
        {applyError && (
          <span
            className="max-w-[14rem] truncate text-xs text-red-600 dark:text-red-400"
            title={applyError}
          >
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
          <Button
            variant="default"
            size="sm"
            className="shrink-0 gap-1.5"
            disabled={applying}
            onClick={() => setModalOpen(true)}
            title="View update details"
          >
            {applying ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                {applyStatus?.message || "Updating…"}
              </>
            ) : (
              <>
                <Download className="h-3.5 w-3.5" />
                Update to v{latestVersion}
              </>
            )}
          </Button>
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
    </>
  );
}
