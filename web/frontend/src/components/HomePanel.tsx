import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
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

interface TileProps {
  icon: LucideIcon;
  label: string;
  description: string;
  badge?: string;
  onClick: () => void;
}

function Tile({ icon: Icon, label, description, badge, onClick }: TileProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex h-full flex-col gap-3 rounded-lg border bg-card p-4 text-left shadow-sm transition-colors hover:border-primary/50 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-center justify-between">
        <span className="flex size-10 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Icon className="h-5 w-5" />
        </span>
        {badge && (
          <span className="rounded-full bg-primary/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-primary">
            {badge}
          </span>
        )}
      </div>
      <div className="flex-1 space-y-1">
        <p className="text-sm font-semibold leading-none">{label}</p>
        <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
      </div>
      <span className="flex items-center gap-1 text-xs font-medium text-primary">
        Open
        <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
      </span>
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
    <section className={cn("space-y-3", className)}>
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{children}</div>
    </section>
  );
}

export function HomePanel({
  desktop,
  updateAvailable,
  onOpenTool,
  onOpenSettings,
}: HomePanelProps) {
  const toolSection = (title: string, subtitle: string, ids: ToolId[]) => (
    <Section title={title} subtitle={subtitle}>
      {ids.map((id) => (
        <Tile
          key={id}
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
      <CardContent className="space-y-8">
        {toolSection("Video", "Convert, cut, join, download, and organize video files.", PRIMARY_TOOLS)}
        {toolSection("Subtitles", "Translate and clean up SRT subtitle files.", SUBTITLE_TOOLS)}
        {toolSection("Experimental", "Specialised utilities for less common jobs.", SECONDARY_TOOLS)}
        <Section title="Settings" className="border-t border-border/60 pt-6">
          {SETTINGS_TILES.filter((s) => desktop || !s.desktopOnly).map((s) => (
            <Tile
              key={s.id}
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
