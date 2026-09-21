/**
 * Applying a theme. A theme mod is data (see core/mods/theme.py): the server has already
 * validated it and resolved every token against the default. This file turns that into CSS
 * variables, and checks each value again before it goes anywhere near a stylesheet, so a value
 * that is not a plain colour, length or font stack can never reach the page.
 */
import type { ThemeData } from "@/lib/types";

export const DEFAULT_THEME_ID = "theme-default";

export type ColorMode = "system" | "light" | "dark";

const STYLE_ID = "toolbox-theme";
const CSS_CACHE_KEY = "toolbox-theme-css";
const MODE_CACHE_KEY = "toolbox-color-mode";

const NAME_RE = /^[a-z][a-z0-9-]*$/;
/** "H S% L%": the form Tailwind reads (`hsl(var(--x))`). */
const TRIPLET_RE = /^-?\d+(\.\d+)? \d+(\.\d+)?% \d+(\.\d+)?%$/;
const RADIUS_RE = /^\d+(\.\d+)?(rem|px)$/;
const FONT_RE = /^[A-Za-z0-9 ,"'_.-]+$/;

function declarations(tokens: Record<string, string>): string {
  return Object.entries(tokens)
    .filter(([name, value]) => NAME_RE.test(name) && TRIPLET_RE.test(value))
    .map(([name, value]) => `--${name}:${value};`)
    .join("");
}

/** The stylesheet for a theme: `:root` for light, `.dark` for dark. Empty for nothing usable. */
export function themeCss(theme: ThemeData): string {
  const { light, dark, radius, font_stack } = theme.resolved;
  const shared =
    (RADIUS_RE.test(radius) ? `--radius:${radius};` : "") +
    (FONT_RE.test(font_stack) ? `--font-sans:${font_stack};` : "");
  return `:root{${declarations(light)}${shared}}.dark{${declarations(dark)}}`;
}

/** Inline variables for a small preview box showing one mode of a theme, whatever the app's mode is. */
export function previewStyle(theme: ThemeData, mode: "light" | "dark"): Record<string, string> {
  const style: Record<string, string> = {};
  for (const [name, value] of Object.entries(theme.resolved[mode])) {
    if (NAME_RE.test(name) && TRIPLET_RE.test(value)) style[`--${name}`] = value;
  }
  if (RADIUS_RE.test(theme.resolved.radius)) style["--radius"] = theme.resolved.radius;
  if (FONT_RE.test(theme.resolved.font_stack)) style["--font-sans"] = theme.resolved.font_stack;
  return style;
}

function setStyleElement(css: string | null): void {
  let el = document.getElementById(STYLE_ID) as HTMLStyleElement | null;
  if (!css) {
    el?.remove();
    return;
  }
  if (!el) {
    el = document.createElement("style");
    el.id = STYLE_ID;
    document.head.appendChild(el);
  }
  el.textContent = css;
}

/** Use `theme`, or the stylesheet's default look when it is null. */
export function applyTheme(theme: ThemeData | null): void {
  const css = theme ? themeCss(theme) : null;
  setStyleElement(css);
  try {
    if (css) localStorage.setItem(CSS_CACHE_KEY, css);
    else localStorage.removeItem(CSS_CACHE_KEY);
  } catch {
    /* storage may be unavailable; the theme still applies for this session */
  }
}

/** Called before the first render so the last theme and mode show at once instead of after a flash. */
export function restoreAppearance(): void {
  try {
    const css = localStorage.getItem(CSS_CACHE_KEY);
    // The cache only ever holds what themeCss produced; anything else is ignored.
    if (css && /^:root\{[^<>{}]*\}\.dark\{[^<>{}]*\}$/.test(css)) setStyleElement(css);
    const mode = readCachedMode();
    const dark = mode === "dark" || (mode === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
  } catch {
    /* ignore */
  }
}

export function readCachedMode(): ColorMode {
  try {
    const value = localStorage.getItem(MODE_CACHE_KEY);
    if (value === "light" || value === "dark" || value === "system") return value;
  } catch {
    /* ignore */
  }
  return "system";
}

export function cacheMode(mode: ColorMode): void {
  try {
    localStorage.setItem(MODE_CACHE_KEY, mode);
  } catch {
    /* ignore */
  }
}

/** A theme as a `mod.toml` the user can save, so the current look can be shared or edited. */
export function themeToToml(name: string, theme: ThemeData): string {
  const hex = (triplet: string): string => {
    const [h, s, l] = triplet.replace(/%/g, "").split(" ").map(Number);
    const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
    const channel = (n: number) => {
      const k = (n + h / 30) % 12;
      const v = l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
      return Math.round(255 * v)
        .toString(16)
        .padStart(2, "0");
    };
    return `#${channel(0)}${channel(8)}${channel(4)}`;
  };
  const id = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/^[^a-z]+/, "");
  const table = (tokens: Record<string, string>) =>
    Object.entries(tokens)
      .map(([token, value]) => `${token} = "${hex(value)}"`)
      .join("\n");
  return [
    `id = "${id || "my-theme"}"`,
    `name = "${name.replace(/"/g, "")}"`,
    'description = "A theme exported from Toolbox."',
    'version = "1.0.0"',
    'author = ""',
    'type = "theme"',
    "api_version = 2",
    "",
    "[theme]",
    `radius = "${theme.resolved.radius}"`,
    `font = "${theme.font ?? "system"}"`,
    "",
    "[theme.light]",
    table(theme.resolved.light),
    "",
    "[theme.dark]",
    table(theme.resolved.dark),
    "",
  ].join("\n");
}
