import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchMods, reloadMods, setModEnabled } from "@/api/client";
import type { ModInfo, ModsResponse } from "@/lib/types";

export interface ModGroup {
  name: string;
  mods: ModInfo[];
}

/** Loads the mods (built-in features and user mods) from the API and keeps them fresh. */
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

  const enabledMods = useMemo(() => (data?.mods ?? []).filter((m) => m.enabled), [data]);

  // The API already sorts mods by group position and order; keep that order.
  const groups = useMemo<ModGroup[]>(() => {
    const out: ModGroup[] = [];
    for (const mod of enabledMods) {
      const existing = out.find((g) => g.name === mod.group);
      if (existing) existing.mods.push(mod);
      else out.push({ name: mod.group, mods: [mod] });
    }
    return out;
  }, [enabledMods]);

  return { data, error, loaded: data !== null, enabledMods, groups, setEnabled, reload };
}

export type ModsState = ReturnType<typeof useMods>;
