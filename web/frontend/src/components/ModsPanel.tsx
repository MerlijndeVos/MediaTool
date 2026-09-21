import { useState } from "react";
import { AlertTriangle, FolderOpen, RefreshCw } from "lucide-react";
import { openModsFolder } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import type { ModsState } from "@/hooks/useMods";
import { modIcon } from "@/lib/modIcons";
import type { ModInfo } from "@/lib/types";

function PermissionChips({ mod }: { mod: ModInfo }) {
  const chips = [
    mod.permissions.network && "Uses the network",
    mod.permissions.writes_files && "Writes files",
    mod.permissions.runs_programs && "Runs programs",
  ].filter(Boolean) as string[];
  if (chips.length === 0) {
    return <span className="text-xs text-muted-foreground">Declares no special access</span>;
  }
  return (
    <span className="flex flex-wrap gap-1.5">
      {chips.map((chip) => (
        <span
          key={chip}
          className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-900 dark:text-amber-200"
        >
          {chip}
        </span>
      ))}
    </span>
  );
}

function ModRow({
  mod,
  onToggle,
}: {
  mod: ModInfo;
  onToggle?: (mod: ModInfo) => void;
}) {
  const Icon = modIcon(mod.icon);
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border/60 p-3">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-sm font-semibold leading-tight">
          {mod.name}
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            v{mod.version}
            {mod.author ? ` · ${mod.author}` : ""}
          </span>
        </p>
        {mod.description && <p className="text-xs text-muted-foreground">{mod.description}</p>}
        <PermissionChips mod={mod} />
        {!mod.builtin && mod.path && (
          <p className="break-all text-[11px] text-muted-foreground">{mod.path}</p>
        )}
      </div>
      {onToggle && (
        <Switch
          checked={mod.enabled}
          onCheckedChange={() => onToggle(mod)}
          aria-label={`${mod.enabled ? "Turn off" : "Turn on"} ${mod.name}`}
        />
      )}
    </div>
  );
}

export function ModsPanel({ mods }: { mods: ModsState }) {
  const { data, setEnabled, reload } = mods;
  const [confirming, setConfirming] = useState<ModInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!data) {
    return (
      <Card className="border-0 shadow-md">
        <CardHeader>
          <CardTitle>Mods</CardTitle>
          <CardDescription>Loading…</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const userMods = data.mods.filter((m) => !m.builtin);
  const builtinMods = data.mods.filter((m) => m.builtin);

  const attempt = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleToggle = (mod: ModInfo) => {
    if (mod.enabled) {
      void attempt(() => setEnabled(mod.id, false));
    } else {
      setConfirming(mod);
    }
  };

  return (
    <Card className="border-0 shadow-md">
      <CardHeader>
        <CardTitle>Mods</CardTitle>
        <CardDescription>
          Mods add tools to Toolbox. The built-in features are mods too; the ones you add
          yourself start turned off.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {data.safe_mode && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
            Safe mode is on: your own mods are not loaded. Restart without{" "}
            <code className="rounded bg-muted px-1">--no-mods</code> to use them.
          </div>
        )}

        <div className="flex gap-3 rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600 dark:text-red-400" />
          <p>
            A mod is code that runs with the same access as Toolbox: it can read, change and
            delete your files. The access a mod declares is only a description, it is not
            enforced. Only turn on mods from people you trust, and read the code first.
          </p>
        </div>

        <section className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Your mods
            </h2>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void attempt(async () => void (await openModsFolder()))}
              >
                <FolderOpen className="h-4 w-4" />
                Open mods folder
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => void attempt(reload)}
              >
                <RefreshCw className="h-4 w-4" />
                Rescan
              </Button>
            </div>
          </div>
          <p className="break-all text-xs text-muted-foreground">
            Folder: <code className="rounded bg-muted px-1">{data.mods_dir}</code>
          </p>

          {userMods.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border/60 p-4 text-sm text-muted-foreground">
              No mods yet. Put a mod folder (one that contains a <code>mod.toml</code>) in the
              folder above, then press Rescan.
            </p>
          ) : (
            <div className="space-y-2">
              {userMods.map((mod) => (
                <div key={mod.id} className="space-y-2">
                  <ModRow mod={mod} onToggle={busy ? undefined : handleToggle} />
                  {confirming?.id === mod.id && (
                    <div className="space-y-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                      <p>
                        Turn on <span className="font-semibold">{mod.name}</span>? It will run
                        code from <code className="break-all rounded bg-muted px-1">{mod.path}</code>{" "}
                        whenever you use it.
                      </p>
                      <div className="flex gap-2">
                        <Button type="button" variant="outline" size="sm" onClick={() => setConfirming(null)}>
                          Cancel
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => {
                            setConfirming(null);
                            void attempt(() => setEnabled(mod.id, true));
                          }}
                        >
                          Turn on
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {data.errors.length > 0 && (
          <section className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Could not load
            </h2>
            {data.errors.map((err) => (
              <div
                key={err.path}
                className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-xs"
              >
                <p className="break-all font-medium">{err.path}</p>
                <p className="text-muted-foreground">{err.message}</p>
              </div>
            ))}
          </section>
        )}

        <section className="space-y-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Built in
          </h2>
          <div className="space-y-2">
            {builtinMods.map((mod) => (
              <ModRow key={mod.id} mod={mod} />
            ))}
          </div>
        </section>

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      </CardContent>
    </Card>
  );
}
