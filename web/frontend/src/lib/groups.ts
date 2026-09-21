/**
 * How each tool category is presented. Which tools belong to which category, and the order of the
 * categories, comes from the API (`group` and `order` in mod.toml, resolved by core/mods/groups.py):
 * the sidebar and the home screen both render that same list, and this file only adds the look and
 * the one-line subtitle. The colours themselves are theme tokens (`--category-*`, see lib/theme.ts).
 */
export type Accent =
  | "files"
  | "media"
  | "subtitles"
  | "experimental"
  | "other"
  | "settings"
  | "primary"
  | "success"
  | "warning"
  | "danger";

/** The accents a mod can ask for with `accent = "..."` in mod.toml. */
export type ModAccent = Accent | "";

interface GroupStyle {
  accent: Accent;
  subtitle?: string;
  /** Quieter menu entries, for categories that are not the everyday ones. */
  muted?: boolean;
}

const GROUP_STYLES: Record<string, GroupStyle> = {
  files: { accent: "files", subtitle: "Rename and organize files and folders." },
  media: { accent: "media", subtitle: "Convert, cut, join, and download video and audio." },
  subtitles: { accent: "subtitles", subtitle: "Translate and clean up SRT subtitle files." },
  experimental: {
    accent: "experimental",
    subtitle: "Specialised utilities for less common jobs.",
    muted: true,
  },
};

const FALLBACK: GroupStyle = { accent: "other" };

export function groupStyle(group: string): GroupStyle {
  return GROUP_STYLES[group.trim().toLowerCase()] ?? FALLBACK;
}

// Full class strings so Tailwind can see them. Category accents come from theme tokens.
export const ACCENT_STYLES: Record<Accent, { tile: string; chip: string }> = {
  files: {
    tile: "bg-category-files/15 hover:bg-category-files/25",
    chip: "bg-category-files text-category-foreground",
  },
  media: {
    tile: "bg-category-media/15 hover:bg-category-media/25",
    chip: "bg-category-media text-category-foreground",
  },
  subtitles: {
    tile: "bg-category-subtitles/15 hover:bg-category-subtitles/25",
    chip: "bg-category-subtitles text-category-foreground",
  },
  experimental: {
    tile: "bg-category-experimental/15 hover:bg-category-experimental/25",
    chip: "bg-category-experimental text-category-foreground",
  },
  other: {
    tile: "bg-category-other/15 hover:bg-category-other/25",
    chip: "bg-category-other text-category-foreground",
  },
  settings: {
    tile: "bg-category-settings/15 hover:bg-category-settings/25",
    chip: "bg-category-settings text-category-foreground",
  },
  primary: {
    tile: "bg-primary/15 hover:bg-primary/25",
    chip: "bg-primary/20 text-primary",
  },
  success: {
    tile: "bg-success/15 hover:bg-success/25",
    chip: "bg-success/25 text-success-text",
  },
  warning: {
    tile: "bg-warning/15 hover:bg-warning/25",
    chip: "bg-warning/25 text-warning-text",
  },
  danger: {
    tile: "bg-danger/15 hover:bg-danger/25",
    chip: "bg-danger/20 text-danger-text",
  },
};
