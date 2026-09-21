import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchSettings, updateSettings } from "@/api/client";
import type { ModInfo } from "@/lib/types";
import {
  type ColorMode,
  DEFAULT_THEME_ID,
  applyTheme,
  cacheMode,
  readCachedMode,
} from "@/lib/theme";

const DARK_QUERY = "(prefers-color-scheme: dark)";

/**
 * The look of the app: which theme mod is active, and light / dark / follow the system.
 *
 * The choice is stored in the app's settings. A theme that is off, removed or not loaded (safe
 * mode) is simply not found, and the default look is used, so the app can never be stranded in a
 * theme that no longer exists.
 */
export function useAppearance(themes: ModInfo[], modsLoaded: boolean) {
  const [themeId, setThemeId] = useState(DEFAULT_THEME_ID);
  const [mode, setModeState] = useState<ColorMode>(readCachedMode);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [systemDark, setSystemDark] = useState(
    () => typeof window !== "undefined" && window.matchMedia(DARK_QUERY).matches,
  );

  useEffect(() => {
    let cancelled = false;
    fetchSettings()
      .then((s) => {
        if (cancelled) return;
        setThemeId(s.theme || DEFAULT_THEME_ID);
        setModeState(s.color_mode);
        cacheMode(s.color_mode);
        setSettingsLoaded(true);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const query = window.matchMedia(DARK_QUERY);
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const dark = mode === "system" ? systemDark : mode === "dark";
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  const active = useMemo(() => themes.find((t) => t.id === themeId) ?? null, [themes, themeId]);
  const activeId = active?.id ?? DEFAULT_THEME_ID;

  // Until the settings and the mod list are both known, keep what restoreAppearance() put on screen.
  const ready = modsLoaded && settingsLoaded;
  useEffect(() => {
    if (!ready) return;
    applyTheme(active && active.id !== DEFAULT_THEME_ID ? active.theme : null);
  }, [ready, active]);

  const selectTheme = useCallback(async (id: string) => {
    setThemeId(id);
    await updateSettings({ theme: id });
  }, []);

  const setMode = useCallback(async (next: ColorMode) => {
    setModeState(next);
    cacheMode(next);
    await updateSettings({ color_mode: next });
  }, []);

  return { themeId: activeId, mode, dark, selectTheme, setMode };
}

export type AppearanceState = ReturnType<typeof useAppearance>;
