/**
 * How each tool group is presented. Which tools belong to which group, and the order of the groups,
 * comes from the mods themselves (`group` and `order` in mod.toml); the sidebar and the home screen
 * both render that same list, and this file only adds the look and the one-line subtitle.
 */
export type GroupAccent = "files" | "media" | "subtitles" | "experimental" | "other";

interface GroupStyle {
  accent: GroupAccent;
  subtitle?: string;
}

const GROUP_STYLES: Record<string, GroupStyle> = {
  files: { accent: "files", subtitle: "Rename and organize files and folders." },
  media: { accent: "media", subtitle: "Convert, cut, join, and download video and audio." },
  subtitles: { accent: "subtitles", subtitle: "Translate and clean up SRT subtitle files." },
  experimental: { accent: "experimental", subtitle: "Specialised utilities for less common jobs." },
};

const FALLBACK: GroupStyle = { accent: "other" };

export function groupStyle(group: string): GroupStyle {
  return GROUP_STYLES[group.trim().toLowerCase()] ?? FALLBACK;
}
