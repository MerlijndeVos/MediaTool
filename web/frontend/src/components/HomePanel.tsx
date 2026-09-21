import type { LucideIcon } from "lucide-react";
import { Bot, Download, Palette, Puzzle, ScrollText } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ModGroup } from "@/hooks/useMods";
import { DelayedTooltip } from "@/components/ui/delayed-tooltip";
import { ACCENT_STYLES, type Accent, groupStyle } from "@/lib/groups";
import { modIcon } from "@/lib/modIcons";
import { cn } from "@/lib/utils";
import type { ToolId } from "@/lib/types";

export type SettingsViewId = "logs" | "ai" | "updates" | "mods" | "appearance";

interface SettingsTile {
  id: SettingsViewId;
  label: string;
  description: string;
  icon: LucideIcon;
  desktopOnly?: boolean;
}

const SETTINGS_TILES: SettingsTile[] = [
  {
    id: "logs",
    label: "Logs",
    description: "Control file logging and open stored log files.",
    icon: ScrollText,
  },
  {
    id: "ai",
    label: "AI",
    description: "Choose OpenAI, Claude, Gemini or a local model for translation and rename profiles.",
    icon: Bot,
  },
  {
    id: "updates",
    label: "Updates",
    description: "Check for new versions and install them.",
    icon: Download,
    desktopOnly: true,
  },
  {
    id: "mods",
    label: "Mods",
    description: "Turn your own mods on or off, and see what is installed.",
    icon: Puzzle,
  },
  {
    id: "appearance",
    label: "Appearance",
    description: "Pick a theme and switch between light and dark.",
    icon: Palette,
  },
];

interface HomePanelProps {
  /** Enabled mods grouped for display (Files, Media, Subtitles, ...). */
  groups: ModGroup[];
  desktop: boolean;
  updateAvailable: boolean;
  onOpenTool: (tool: ToolId) => void;
  onOpenSettings: (view: SettingsViewId) => void;
}

interface TileProps {
  accent: Accent;
  icon: LucideIcon;
  label: string;
  description: string;
  badge?: string;
  onClick: () => void;
}

function Tile({ accent, icon: Icon, label, description, badge, onClick }: TileProps) {
  const styles = ACCENT_STYLES[accent];
  return (
    <DelayedTooltip content={description}>
      {(trigger) => (
        <button
          {...trigger}
          type="button"
          onClick={onClick}
          className={cn(
            "flex min-w-0 items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            styles.tile,
          )}
        >
          <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-md", styles.chip)}>
            <Icon className="h-4 w-4" />
          </span>
          <span className="min-w-0 flex-1 truncate text-sm font-semibold">{label}</span>
          {badge && (
            <span className="shrink-0 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold uppercase text-primary-foreground">
              {badge}
            </span>
          )}
        </button>
      )}
    </DelayedTooltip>
  );
}

function Section({
  title,
  subtitle,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("space-y-2.5", className)}>
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(10.5rem,1fr))] gap-2">{children}</div>
    </section>
  );
}

export function HomePanel({
  groups,
  desktop,
  updateAvailable,
  onOpenTool,
  onOpenSettings,
}: HomePanelProps) {
  return (
    <Card className="border-0 shadow-md">
      <CardHeader>
        <CardTitle>Welcome to Toolbox</CardTitle>
        <CardDescription>Pick a tool to get started.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {groups.map((group) => {
          const { accent, subtitle } = groupStyle(group.name);
          return (
            <Section key={group.name} title={group.name} subtitle={subtitle}>
              {group.mods.map((mod) => (
                <Tile
                  key={mod.id}
                  accent={mod.accent || accent}
                  icon={modIcon(mod.icon)}
                  label={mod.name}
                  description={mod.description}
                  onClick={() => onOpenTool(mod.id)}
                />
              ))}
            </Section>
          );
        })}
        <Section title="Settings" className="border-t border-border/60 pt-5">
          {SETTINGS_TILES.filter((s) => desktop || !s.desktopOnly).map((s) => (
            <Tile
              key={s.id}
              accent="settings"
              icon={s.icon}
              label={s.label}
              description={s.description}
              badge={s.id === "updates" && updateAvailable ? "New" : undefined}
              onClick={() => onOpenSettings(s.id)}
            />
          ))}
        </Section>
      </CardContent>
    </Card>
  );
}
