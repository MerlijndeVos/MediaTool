import { useEffect, useRef, useState } from "react";
import { FolderOpen, RefreshCw, ShieldAlert, ShieldCheck, Trash2 } from "lucide-react";
import {
  cancelModInstall,
  checkModUpdate,
  confirmModInstall,
  fetchModPrompts,
  fetchModSource,
  openModsFolder,
  prepareModUpdate,
  removeMod,
  setModsSafeMode,
} from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { CodeFiles, CopyButton, PermissionChips, PlacementChip, TrustNotice } from "@/components/ModBits";
import { Swatches } from "@/components/ThemePreview";
import { ModAddForm } from "@/components/ModAddForm";
import { ModInstallReview, describeSource } from "@/components/ModInstallReview";
import { ModMarket } from "@/components/ModMarket";
import type { ModsState } from "@/hooks/useMods";
import { modIcon } from "@/lib/modIcons";
import type { ModInfo, ModInstallPreview, ModNotice, ModSourceFile, ModUpdateStatus } from "@/lib/types";

function ModRow({
  mod,
  notices = [],
  onToggle,
  children,
}: {
  mod: ModInfo;
  notices?: ModNotice[];
  onToggle?: (mod: ModInfo) => void;
  children?: React.ReactNode;
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
            {mod.author ? ` — ${mod.author}` : ""}
          </span>
        </p>
        {mod.description && <p className="text-xs text-muted-foreground">{mod.description}</p>}
        <div className="flex flex-wrap items-center gap-2">
          <PlacementChip type={mod.type} group={mod.group} />
          {mod.type === "tool" && <PermissionChips permissions={mod.permissions} />}
        </div>
        {mod.theme && <Swatches colors={mod.theme.swatches.light} className="w-40" />}
        {mod.theme?.warnings.map((w) => (
          <p key={w} className="text-[11px] text-warning-text">
            {w}
          </p>
        ))}
        {notices.map((n) => (
          <p key={n.message} className="text-[11px] text-warning-text">
            {n.message}
          </p>
        ))}
        {children}
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

interface UserModItemProps {
  mod: ModInfo;
  notices: ModNotice[];
  busy: boolean;
  onToggle: (mod: ModInfo) => void;
  onReview: (preview: ModInstallPreview) => void;
  onRemove: (mod: ModInfo) => Promise<void>;
  onError: (message: string) => void;
}

function UserModItem({ mod, notices, busy, onToggle, onReview, onRemove, onError }: UserModItemProps) {
  const [files, setFiles] = useState<ModSourceFile[] | null>(null);
  const [update, setUpdate] = useState<ModUpdateStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [removing, setRemoving] = useState(false);
  const install = mod.install;
  const isGit = install?.type === "git";

  const guard = async (fn: () => Promise<void>) => {
    try {
      await fn();
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    }
  };

  const toggleCode = () =>
    guard(async () => setFiles(files ? null : (await fetchModSource(mod.id)).files));

  const check = async () => {
    setChecking(true);
    await guard(async () => setUpdate(await checkModUpdate(mod.id)));
    setChecking(false);
  };

  return (
    <div className="space-y-2">
      <ModRow mod={mod} notices={notices} onToggle={busy ? undefined : onToggle}>
        <p className="break-all text-[11px] text-muted-foreground">
          {install ? (
            <>
              {describeSource(install)}
              {isGit && install.commit && <> — commit {install.commit.slice(0, 10)}</>}
            </>
          ) : (
            <>Added by hand — {mod.path}</>
          )}
        </p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 text-xs">
          <button type="button" className="text-primary hover:underline" onClick={() => void toggleCode()}>
            {files ? "Hide " : "View "}{mod.type === "theme" ? "file" : "code"}
          </button>
          {isGit && (
            <button
              type="button"
              className="text-primary hover:underline disabled:opacity-50"
              disabled={checking || busy}
              onClick={() => void check()}
            >
              {checking ? "Checking…" : "Check for updates"}
            </button>
          )}
          {update &&
            (!update.supported ? (
              <span className="text-muted-foreground">{update.reason}</span>
            ) : update.available ? (
              <button
                type="button"
                className="font-medium text-warning-text hover:underline"
                disabled={busy}
                onClick={() => void guard(async () => onReview(await prepareModUpdate(mod.id)))}
              >
                Update available: review changes
              </button>
            ) : (
              <span className="text-muted-foreground">Up to date</span>
            ))}
          <button
            type="button"
            className="inline-flex items-center gap-1 text-danger-text hover:underline"
            disabled={busy}
            onClick={() => setRemoving(true)}
          >
            <Trash2 className="h-3 w-3" />
            Remove
          </button>
        </div>
      </ModRow>
      {files && <CodeFiles files={files} />}
      {removing && (
        <div className="space-y-3 rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm">
          <p>
            Remove <span className="font-semibold">{mod.name}</span>? Its folder is deleted from
            your computer. Files the mod created elsewhere are not touched.
          </p>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setRemoving(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={() => {
                setRemoving(false);
                void onRemove(mod);
              }}
            >
              Remove
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

type Tab = "installed" | "browse";

export function ModsPanel({ mods }: { mods: ModsState }) {
  const { data, setEnabled, reload } = mods;
  const [tab, setTab] = useState<Tab>("installed");
  const [confirming, setConfirming] = useState<ModInfo | null>(null);
  const [review, setReview] = useState<ModInstallPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // A staged mod that is never confirmed would sit in the staging folder; drop it when the panel goes away.
  const staged = useRef<string | null>(null);
  staged.current = review?.token ?? null;
  useEffect(
    () => () => {
      if (staged.current) void cancelModInstall(staged.current).catch(() => undefined);
    },
    [],
  );

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

  const showReview = (preview: ModInstallPreview) => {
    if (review) void cancelModInstall(review.token).catch(() => undefined);
    setReview(preview);
    setTab("installed");
  };

  const dropReview = () => {
    if (review) void cancelModInstall(review.token).catch(() => undefined);
    setReview(null);
  };

  const handleToggle = (mod: ModInfo) => {
    // A theme is data with no code, so there is nothing to confirm; a tool runs code from its folder.
    if (mod.enabled || mod.type === "theme") {
      void attempt(() => setEnabled(mod.id, !mod.enabled));
    } else {
      setConfirming(mod);
    }
  };

  return (
    <Card className="border-0 shadow-md">
      <CardHeader>
        <CardTitle>Mods</CardTitle>
        <CardDescription>
          Mods add tools and themes to Toolbox. The built-in features are mods too; the ones you
          add yourself start turned off unless you choose otherwise.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {data.safe_mode && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm">
            <span>Safe mode is on: your own mods are not loaded.</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() =>
                void attempt(async () => {
                  await setModsSafeMode(false);
                  await reload();
                })
              }
            >
              <ShieldCheck className="h-4 w-4" />
              Turn safe mode off
            </Button>
          </div>
        )}

        <TrustNotice />

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div role="tablist" aria-label="Mods" className="flex gap-1 rounded-lg bg-muted p-1">
            {(
              [
                ["installed", "Your mods"],
                ["browse", "Browse"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={
                  "rounded-md px-3 py-1 text-sm font-medium transition-colors " +
                  (tab === id ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground")
                }
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <CopyButton
              onFailed={setError}
              getText={async () => (await fetchModPrompts()).build}
              title="Copy a prompt that tells an AI assistant how to write a mod for you"
            >
              Copy AI prompt
            </CopyButton>
            <CopyButton
              onFailed={setError}
              getText={async () => (await fetchModPrompts()).theme}
              title="Copy a prompt that tells an AI assistant how to design a theme for you"
            >
              Copy AI theme prompt
            </CopyButton>
            {!data.safe_mode && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                title="Turn every mod you added off until Toolbox restarts"
                onClick={() =>
                  void attempt(async () => {
                    await setModsSafeMode(true);
                    await reload();
                  })
                }
              >
                <ShieldAlert className="h-4 w-4" />
                Safe mode
              </Button>
            )}
          </div>
        </div>

        {review && (
          <ModInstallReview
            preview={review}
            busy={busy}
            onError={setError}
            onCancel={dropReview}
            onConfirm={(enable) =>
              void attempt(async () => {
                await confirmModInstall(review.token, enable);
                setReview(null);
                await reload();
              })
            }
          />
        )}

        {tab === "browse" ? (
          <ModMarket
            installedIds={new Set(userMods.map((m) => m.id))}
            busy={busy}
            onBusy={setBusy}
            onPrepared={showReview}
            onError={(message) => setError(message || null)}
          />
        ) : (
          <>
            <ModAddForm
              busy={busy}
              onBusy={setBusy}
              onPrepared={showReview}
              onError={(message) => setError(message || null)}
            />

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
                  No mods yet. Add one above, or find one under Browse. A mod folder you copy into
                  the folder above shows up after Rescan.
                </p>
              ) : (
                <div className="space-y-2">
                  {userMods.map((mod) => (
                    <div key={mod.id} className="space-y-2">
                      <UserModItem
                        mod={mod}
                        notices={data.notices.filter((n) => n.id === mod.id)}
                        busy={busy}
                        onToggle={handleToggle}
                        onReview={showReview}
                        onError={setError}
                        onRemove={(m) =>
                          attempt(async () => {
                            await removeMod(m.id);
                            await reload();
                          })
                        }
                      />
                      {confirming?.id === mod.id && (
                        <div className="space-y-3 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
                          <p>
                            Turn on <span className="font-semibold">{mod.name}</span>? It will run
                            code from{" "}
                            <code className="break-all rounded bg-muted px-1">{mod.path}</code>{" "}
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
                    className="rounded-lg border border-danger/30 bg-danger/5 p-3 text-xs"
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
                  <ModRow key={mod.id} mod={mod} notices={data.notices.filter((n) => n.id === mod.id)} />
                ))}
              </div>
            </section>
          </>
        )}

        {error && <p className="text-sm text-danger-text">{error}</p>}
      </CardContent>
    </Card>
  );
}
