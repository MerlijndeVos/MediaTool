import type { LucideIcon } from "lucide-react";
import {
  AudioLines,
  Bot,
  Combine,
  Copy,
  Disc3,
  Download,
  Eraser,
  FileVideo,
  FolderPen,
  Languages,
  Palette,
  PenLine,
  Scissors,
  ScrollText,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  PRIMARY_TOOLS,
  SECONDARY_TOOLS,
  SUBTITLE_TOOLS,
  TOOL_LABELS,
  toolDescription,
  type ToolId,
} from "@/lib/types";

export type SettingsViewId = "logs" | "openai" | "updates" | "appearance";

const TOOL_ICONS: Record<ToolId, LucideIcon> = {
  convert: FileVideo,
  trim: Scissors,
  stitch: Combine,
  download: Download,
  rename: PenLine,
  vts: Disc3,
  audio: AudioLines,
  dedup: Copy,
  rename_folders: FolderPen,
  subtitle_translate: Languages,
  subtitle_cleanup: Eraser,
};

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
    id: "openai",
    label: "OpenAI",
    description: "API key and model used for subtitle translation.",
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
    id: "appearance",
    label: "Appearance",
    description: "Switch between light and dark themes.",
    icon: Palette,
  },
];

interface HomePanelProps {
  desktop: boolean;
  updateAvailable: boolean;
  onOpenTool: (tool: ToolId) => void;
  onOpenSettings: (view: SettingsViewId) => void;
}

type Accent = "video" | "subtitles" | "experimental" | "settings";

// Full class strings so Tailwind can see them.
const ACCENT_STYLES: Record<Accent, { tile: string; chip: string }> = {
  video: {
    tile: "bg-blue-500/15 hover:bg-blue-500/25",
    chip: "bg-blue-600 text-white dark:bg-blue-500",
  },
  subtitles: {
    tile: "bg-violet-500/15 hover:bg-violet-500/25",
    chip: "bg-violet-600 text-white dark:bg-violet-500",
  },
  experimental: {
    tile: "bg-amber-500/15 hover:bg-amber-500/25",
    chip: "bg-amber-600 text-white dark:bg-amber-500",
  },
  settings: {
    tile: "bg-slate-500/15 hover:bg-slate-500/25",
    chip: "bg-slate-600 text-white dark:bg-slate-500",
  },
};

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
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        styles.tile,
      )}
    >
      <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-md", styles.chip)}>
        <Icon className="h-[18px] w-[18px]" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold leading-tight">{label}</span>
        <span className="mt-0.5 line-clamp-2 block text-xs leading-snug text-muted-foreground">
          {description}
        </span>
      </span>
      {badge && (
        <span className="shrink-0 self-start rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold uppercase text-primary-foreground">
          {badge}
        </span>
      )}
    </button>
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
      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">{children}</div>
    </section>
  );
}

export function HomePanel({
  desktop,
  updateAvailable,
  onOpenTool,
  onOpenSettings,
}: HomePanelProps) {
  const toolSection = (accent: Accent, title: string, subtitle: string, ids: ToolId[]) => (
    <Section title={title} subtitle={subtitle}>
      {ids.map((id) => (
        <Tile
          key={id}
          accent={accent}
          icon={TOOL_ICONS[id]}
          label={TOOL_LABELS[id]}
          description={toolDescription(id)}
          onClick={() => onOpenTool(id)}
        />
      ))}
    </Section>
  );

  return (
    <Card className="border-0 shadow-md">
      <CardHeader>
        <CardTitle>Welcome to Media Tool</CardTitle>
        <CardDescription>Pick a tool to get started.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {toolSection("video", "Video", "Convert, cut, join, download, and organize video files.", PRIMARY_TOOLS)}
        {toolSection("subtitles", "Subtitles", "Translate and clean up SRT subtitle files.", SUBTITLE_TOOLS)}
        {toolSection("experimental", "Experimental", "Specialised utilities for less common jobs.", SECONDARY_TOOLS)}
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
