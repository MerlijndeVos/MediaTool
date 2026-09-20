import type { LucideIcon } from "lucide-react";
import {
  Archive,
  AudioLines,
  Combine,
  Copy,
  Disc3,
  Download,
  Eraser,
  FileText,
  FileVideo,
  Film,
  Folder,
  FolderPen,
  Image,
  Languages,
  Music,
  PenLine,
  Puzzle,
  Scissors,
  Search,
  Sparkles,
  Tag,
  Wrench,
} from "lucide-react";

/** Icon names a mod can put in `icon = "..."` (lucide names, kebab-case). */
const MOD_ICONS: Record<string, LucideIcon> = {
  archive: Archive,
  "audio-lines": AudioLines,
  combine: Combine,
  copy: Copy,
  "disc-3": Disc3,
  download: Download,
  eraser: Eraser,
  "file-text": FileText,
  "file-video": FileVideo,
  film: Film,
  folder: Folder,
  "folder-pen": FolderPen,
  image: Image,
  languages: Languages,
  music: Music,
  "pen-line": PenLine,
  puzzle: Puzzle,
  scissors: Scissors,
  search: Search,
  sparkles: Sparkles,
  tag: Tag,
  wrench: Wrench,
};

export function modIcon(name: string): LucideIcon {
  return MOD_ICONS[name] ?? Puzzle;
}

export type GroupAccent = "video" | "subtitles" | "experimental" | "other";

export function groupAccent(group: string): GroupAccent {
  const key = group.trim().toLowerCase();
  if (key === "video") return "video";
  if (key === "subtitles") return "subtitles";
  if (key === "experimental") return "experimental";
  return "other";
}
