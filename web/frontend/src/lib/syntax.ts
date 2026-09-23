/**
 * Syntax highlighting for code and log previews. Code goes through highlight.js (lib/highlighter.ts,
 * loaded on first use); log lines through the small tokenizer below. Both produce the `hljs-*`
 * classes that index.css colours from the active scheme.
 */
import { useSyncExternalStore } from "react";

export type SyntaxScheme = "theme" | "github" | "one" | "contrast";

export const SCHEMES: { id: SyntaxScheme; label: string; description: string }[] = [
  { id: "theme", label: "From the theme", description: "The colours of the theme in use." },
  { id: "github", label: "GitHub", description: "The colours of code on GitHub." },
  { id: "one", label: "One", description: "Atom's One Light and One Dark." },
  { id: "contrast", label: "High contrast", description: "Strong colours, at least 7:1 on plain backgrounds." },
];

export interface SyntaxSettings {
  code: boolean;
  logs: boolean;
  scheme: SyntaxScheme;
}

export const DEFAULT_SYNTAX: SyntaxSettings = { code: true, logs: true, scheme: "theme" };

// The current settings, shared by every preview. useAppearance keeps them in step with the app's settings.
let current = DEFAULT_SYNTAX;
const listeners = new Set<() => void>();

export function setSyntaxSettings(next: SyntaxSettings): void {
  if (next.code === current.code && next.logs === current.logs && next.scheme === current.scheme) return;
  current = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useSyntax(): SyntaxSettings {
  return useSyncExternalStore(subscribe, () => current);
}

export function isScheme(value: unknown): value is SyntaxScheme {
  return SCHEMES.some((s) => s.id === value);
}

const SCHEME_CACHE_KEY = "toolbox-syntax-scheme";

/** Use `scheme` for every preview in the app (a data-syntax attribute on <html>). */
export function applySyntaxScheme(scheme: SyntaxScheme): void {
  document.documentElement.dataset.syntax = scheme;
  try {
    localStorage.setItem(SCHEME_CACHE_KEY, scheme);
  } catch {
    /* ignore */
  }
}

/** Called before the first render, like restoreAppearance, so previews do not change colour on load. */
export function restoreSyntaxScheme(): void {
  try {
    const scheme = localStorage.getItem(SCHEME_CACHE_KEY);
    if (isScheme(scheme)) document.documentElement.dataset.syntax = scheme;
  } catch {
    /* ignore */
  }
}

// --------------------------------------------------------------------------------------------
// Code
// --------------------------------------------------------------------------------------------

/** Longer text is shown plain: highlighting it would make the preview slow to open. */
export const MAX_CODE_CHARS = 200_000;

const LANGUAGES: Record<string, string> = {
  py: "python",
  pyw: "python",
  toml: "ini",
  ini: "ini",
  cfg: "ini",
  conf: "ini",
  json: "json",
  md: "markdown",
  markdown: "markdown",
  js: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  jsx: "javascript",
  ts: "typescript",
  mts: "typescript",
  tsx: "typescript",
  css: "css",
  yml: "yaml",
  yaml: "yaml",
  html: "xml",
  htm: "xml",
  xml: "xml",
  svg: "xml",
  sh: "bash",
  bash: "bash",
};

/** The highlight.js language for a file, from its extension; null for plain text. */
export function languageFor(path: string): string | null {
  const name = path.split(/[\\/]/).pop() ?? "";
  const dot = name.lastIndexOf(".");
  if (dot < 0) return null;
  return LANGUAGES[name.slice(dot + 1).toLowerCase()] ?? null;
}

let highlighter: Promise<typeof import("@/lib/highlighter")> | null = null;

export function loadHighlighter() {
  highlighter ??= import("@/lib/highlighter").catch((e) => {
    highlighter = null; // let a later preview try again
    throw e;
  });
  return highlighter;
}

// --------------------------------------------------------------------------------------------
// Logs
// --------------------------------------------------------------------------------------------

export interface LogToken {
  text: string;
  /** Class names for the span; undefined for plain text. */
  className?: string;
}

/** Longer lines are shown plain. */
export const MAX_LOG_LINE_CHARS = 4000;

// One alternative per kind of token, tried left to right at each position; earlier ones win.
const LOG_TOKEN = new RegExp(
  [
    /(?<timestamp>\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b|\b\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b)/,
    /(?<level>\[(?:DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)\])/,
    /(?<url>\bhttps?:\/\/[^\s"'<>)\]]+)/,
    /(?<string>"(?:[^"\\]|\\.)*"|(?<![\w'])'(?:[^'\\]|\\.)*'(?![\w']))/,
    /(?<path>\b[A-Za-z]:[\\/][^\s"'<>|*?]*|(?<![\w.:/])(?:~|\.{1,2})?\/(?:[\w.@+-]+\/)*[\w.@+-]+\/?)/,
    /(?<traceback>^Traceback\b)/,
    /(?<exception>\b[A-Z]\w*(?:Error|Exception|Warning|Interrupt|Exit)\b)/,
    /(?<literal>\b(?:True|False|None|true|false|null)\b)/,
    /(?<key>\b[A-Za-z_][\w.-]*(?==[^=\s]))/,
    /(?<number>(?<![\w.])[-+]?\d+(?:[.,]\d+)?(?:%|[kKMGT]i?B|[kKMG]b?ps|ms|s|x|fps|Hz|kHz)?(?![\w]))/,
  ]
    .map((r) => r.source)
    .join("|"),
  "g",
);

const TOKEN_CLASS: Record<string, string> = {
  timestamp: "hl-timestamp",
  url: "hljs-string underline decoration-dotted underline-offset-2",
  string: "hljs-string",
  path: "hljs-title function_",
  traceback: "hljs-keyword",
  exception: "hljs-type",
  literal: "hljs-literal",
  key: "hljs-attr",
  number: "hljs-number",
};

function levelClass(tag: string): string {
  if (tag === "[ERROR]" || tag === "[CRITICAL]" || tag === "[FATAL]") return "font-semibold text-log-error";
  if (tag === "[WARNING]" || tag === "[WARN]") return "font-semibold text-log-warn";
  return "hljs-keyword";
}

/** Split a log line into coloured pieces: timestamps, level tags, paths, URLs, strings, numbers and so on. */
export function tokenizeLog(line: string): LogToken[] {
  if (line.length > MAX_LOG_LINE_CHARS) return [{ text: line }];
  const tokens: LogToken[] = [];
  let last = 0;
  LOG_TOKEN.lastIndex = 0;
  for (let m = LOG_TOKEN.exec(line); m; m = LOG_TOKEN.exec(line)) {
    if (m[0] === "") {
      LOG_TOKEN.lastIndex += 1;
      continue;
    }
    const kind = Object.keys(TOKEN_CLASS).concat("level").find((k) => m!.groups?.[k] !== undefined);
    if (!kind) continue;
    if (m.index > last) tokens.push({ text: line.slice(last, m.index) });
    tokens.push({ text: m[0], className: kind === "level" ? levelClass(m[0]) : TOKEN_CLASS[kind] });
    last = m.index + m[0].length;
  }
  if (last < line.length) tokens.push({ text: line.slice(last) });
  return tokens;
}
