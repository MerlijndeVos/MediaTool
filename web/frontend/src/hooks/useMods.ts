import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchMods, reloadMods, setModEnabled } from "@/api/client";
import type { ModInfo, ModsResponse } from "@/lib/types";

export interface ModGroup {
  name: string;
  mods: ModInfo[];
}

/** Loads the mods (built-in features, user mods and themes) from the API and keeps them fresh. */
export function useMods() {
  const [data, setData] = useState<ModsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The API may still be starting; keep trying until the first response arrives.
  useEffect(() => {
    if (data) return;
    let cancelled = false;
    const load = () =>
      fetchMods()
        .then((res) => {
          if (!cancelled) setData(res);
        })
        .catch((e) => {
          if (!cancelled) setError(e instanceof Error ? e.message : String(e));
        });
    load();
    const id = setInterval(load, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [data]);

  const setEnabled = useCallback(async (id: string, enabled: boolean) => {
    setData(await setModEnabled(id, enabled));
  }, []);

  const reload = useCallback(async () => {
    setData(await reloadMods());
  }, []);

  // Tools (what the sidebar and home screen list) and themes (what Appearance offers) are both mods.
  const enabledMods = useMemo(
    () => (data?.mods ?? []).filter((m) => m.enabled && m.type === "tool"),
    [data],
  );
  const themes = useMemo(
    () => (data?.mods ?? []).filter((m) => m.enabled && m.type === "theme"),
    [data],
  );

  // The API already sorts mods by section (built-in ones first, then new ones A to Z) and order; keep that order.
  const groups = useMemo<ModGroup[]>(() => {
    const out: ModGroup[] = [];
    for (const mod of enabledMods) {
      const existing = out.find((g) => g.name === mod.group);
      if (existing) existing.mods.push(mod);
      else out.push({ name: mod.group, mods: [mod] });
    }
    return out;
  }, [enabledMods]);

  return { data, error, loaded: data !== null, enabledMods, themes, groups, setEnabled, reload };
}

export type ModsState = ReturnType<typeof useMods>;
