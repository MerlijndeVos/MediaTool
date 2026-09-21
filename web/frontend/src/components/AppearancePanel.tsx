import { useState } from "react";
import { AlertTriangle, Check, Monitor, Moon, RotateCcw, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CopyButton } from "@/components/ModBits";
import { Swatches, ThemePreview } from "@/components/ThemePreview";
import type { AppearanceState } from "@/hooks/useAppearance";
import { type ColorMode, DEFAULT_THEME_ID, themeToToml } from "@/lib/theme";
import type { ModInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

interface AppearancePanelProps {
  appearance: AppearanceState;
  /** The themes that are on (the default one is always among them). */
  themes: ModInfo[];
  onOpenMods: () => void;
}

const MODES: { id: ColorMode; label: string; icon: typeof Sun }[] = [
  { id: "light", label: "Light", icon: Sun },
  { id: "dark", label: "Dark", icon: Moon },
  { id: "system", label: "Follow system", icon: Monitor },
];

export function AppearancePanel({ appearance, themes, onOpenMods }: AppearancePanelProps) {
  const { themeId, mode, dark, selectTheme, setMode } = appearance;
  const [error, setError] = useState<string | null>(null);
  const active = themes.find((t) => t.id === themeId);

  const guard = (fn: () => Promise<void>) => {
    setError(null);
    fn().catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  return (
    <Card className="border-0 shadow-md">
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
        <CardDescription>
          Choose a theme and whether Toolbox is light or dark. A theme only changes colours,
          corners and the font: it is data, and no code runs.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <section className="space-y-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Mode</h2>
          <div role="radiogroup" aria-label="Light or dark" className="flex flex-wrap gap-2">
            {MODES.map(({ id, label, icon: Icon }) => (
              <Button
                key={id}
                type="button"
                role="radio"
                aria-checked={mode === id}
                variant={mode === id ? "default" : "outline"}
                onClick={() => guard(() => setMode(id))}
                className="gap-1.5"
              >
                <Icon className="h-4 w-4" />
                {label}
              </Button>
            ))}
          </div>
          <p className="text-sm text-muted-foreground">
            {mode === "system"
              ? `Following your system: ${dark ? "dark" : "light"} right now.`
              : `${dark ? "Dark" : "Light"} is always used.`}
          </p>
        </section>

        <section className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Theme</h2>
            <div className="flex flex-wrap gap-2">
              {active?.theme && (
                <CopyButton
                  title="Copy the current look as a theme file you can edit and share"
                  getText={() => themeToToml(`${active.name} copy`, active.theme!)}
                  onFailed={setError}
                >
                  Copy as theme file
                </CopyButton>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={themeId === DEFAULT_THEME_ID}
                onClick={() => guard(() => selectTheme(DEFAULT_THEME_ID))}
              >
                <RotateCcw className="h-4 w-4" />
                Reset to default
              </Button>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            {themes.map((theme) => {
              const selected = theme.id === themeId;
              const data = theme.theme;
              if (!data) return null;
              return (
                <div
                  key={theme.id}
                  className={cn(
                    "space-y-2.5 rounded-lg border p-3 transition-colors",
                    selected ? "border-primary ring-1 ring-primary" : "border-border/60",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold leading-tight">
                        {theme.name}
                        {theme.builtin && (
                          <span className="ml-2 text-xs font-normal text-muted-foreground">Built in</span>
                        )}
                      </p>
                      {theme.description && (
                        <p className="text-xs text-muted-foreground">{theme.description}</p>
                      )}
                      {!theme.builtin && theme.author && (
                        <p className="text-[11px] text-muted-foreground">by {theme.author}</p>
                      )}
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant={selected ? "secondary" : "default"}
                      aria-pressed={selected}
                      disabled={selected}
                      onClick={() => guard(() => selectTheme(theme.id))}
                    >
                      {selected ? (
                        <>
                          <Check className="h-4 w-4" /> In use
                        </>
                      ) : (
                        "Use"
                      )}
                    </Button>
                  </div>
                  <Swatches colors={data.swatches[dark ? "dark" : "light"]} />
                  <div className="grid gap-2 sm:grid-cols-2">
                    <ThemePreview theme={data} mode="light" />
                    <ThemePreview theme={data} mode="dark" />
                  </div>
                  {data.warnings.length > 0 && (
                    <div className="space-y-1 rounded-md border border-warning/40 bg-warning/10 p-2 text-xs">
                      <p className="flex items-center gap-1.5 font-medium text-warning-text">
                        <AlertTriangle className="h-3.5 w-3.5" /> Hard to read in places
                      </p>
                      <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
                        {data.warnings.map((w) => (
                          <li key={w}>{w}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <p className="text-sm text-muted-foreground">
            More themes: add one under{" "}
            <button type="button" className="text-primary hover:underline" onClick={onOpenMods}>
              Settings → Mods
            </button>{" "}
            (paste a git address, choose a folder, zip or .toml file, or browse the market). A theme
            that would make warnings or the Remove button unreadable is refused.
          </p>
        </section>

        {error && <p className="text-sm text-danger-text">{error}</p>}
      </CardContent>
    </Card>
  );
}
