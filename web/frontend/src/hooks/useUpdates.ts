import { useCallback, useEffect, useState } from "react";
import {
  applyUpdate,
  checkForUpdates,
  fetchUpdateStatus,
  type UpdateApplyStatus,
  type UpdateCheck,
} from "@/api/client";
import { isDesktopApp } from "@/lib/desktop";
import { isNewerVersionAvailable } from "@/lib/version";

const CHECK_INTERVAL_MS = 60 * 60 * 1000;
const SKIPPED_UPDATE_KEY = "media-tool-skipped-update";

export function useUpdates() {
  const [check, setCheck] = useState<UpdateCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [networkError, setNetworkError] = useState<string | null>(null);
  const [applyStatus, setApplyStatus] = useState<UpdateApplyStatus | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const desktop = isDesktopApp();

  const runCheck = useCallback(async () => {
    if (!desktop) return;
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
  }, [desktop]);

  useEffect(() => {
    if (!desktop) return;
    runCheck();
    const id = setInterval(runCheck, CHECK_INTERVAL_MS);
    return () => clearInterval(id);
  }, [desktop, runCheck]);

  const applying = applyStatus?.phase === "downloading" || applyStatus?.phase === "installing";
  const showUpdate = Boolean(
    check &&
      check.can_install &&
      check.latest_version &&
      isNewerVersionAvailable(check.current_version, check.latest_version, check.update_available),
  );

  useEffect(() => {
    if (!desktop || !showUpdate || !check?.latest_version || applying) return;
    const skipped = localStorage.getItem(SKIPPED_UPDATE_KEY);
    if (skipped !== check.latest_version) {
      setModalOpen(true);
    }
  }, [desktop, showUpdate, check?.latest_version, applying]);

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

  return {
    desktop,
    check,
    checking,
    networkError,
    applyStatus,
    applyError,
    applying,
    showUpdate,
    modalOpen,
    setModalOpen,
    runCheck,
    handleApply,
    handleSkip,
  };
}

export type UpdatesState = ReturnType<typeof useUpdates>;
