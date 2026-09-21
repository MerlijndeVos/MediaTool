import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, Check, Copy, Loader2, RefreshCw, Search, WrapText, X } from "lucide-react";
import { fetchLogChunk } from "@/api/client";
import { LogStream } from "@/components/LogStream";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn, formatBytes } from "@/lib/utils";
import type { LogLine } from "@/lib/types";

/** How many lines each request loads: the end of the file first, then this many more per "load earlier". */
const PAGE_LINES = 500;

type Level = "error" | "warning" | "info";

const LEVELS: { id: Level; label: string; value: number; dot: string }[] = [
  { id: "error", label: "Errors", value: 40, dot: "bg-red-500" },
  { id: "warning", label: "Warnings", value: 30, dot: "bg-amber-500" },
  { id: "info", label: "Info", value: 20, dot: "bg-muted-foreground/60" },
];

// Lines are written as "2026-01-01 12:00:00,123 [LEVEL] message".
const LEVEL_TAG = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)? \[([A-Z]+)\]/;

function tagToLevel(tag: string): Level {
  if (tag === "ERROR" || tag === "CRITICAL" || tag === "FATAL") return "error";
  if (tag === "WARNING" || tag === "WARN") return "warning";
  return "info";
}

interface Entry {
  text: string;
  level: Level;
}

/** Give every line a level. Lines without a tag (a traceback, wrapped text) belong to the line above. */
function classify(lines: string[]): Entry[] {
  let current: Level = "info";
  return lines.map((text) => {
    const tag = LEVEL_TAG.exec(text);
    if (tag) current = tagToLevel(tag[1]);
    return { text, level: current };
  });
}

type ScrollAction = { kind: "bottom" } | { kind: "keep"; height: number; top: number };

export function LogFileViewer({ name, onClose }: { name: string; onClose: () => void }) {
  const [lines, setLines] = useState<string[]>([]);
  const [start, setStart] = useState(0);
  const [hasEarlier, setHasEarlier] = useState(false);
  const [sizeBytes, setSizeBytes] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [shown, setShown] = useState<Record<Level, boolean>>({ error: true, warning: true, info: true });
  const [wrap, setWrap] = useState(true);
  const [copied, setCopied] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const pendingScroll = useRef<ScrollAction | null>(null);
  const requestId = useRef(0);

  const loadTail = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const chunk = await fetchLogChunk(name, { lines: PAGE_LINES });
      if (id !== requestId.current) return;
      pendingScroll.current = { kind: "bottom" };
      setLines(chunk.lines);
      setStart(chunk.start);
      setHasEarlier(chunk.has_earlier);
      setSizeBytes(chunk.size_bytes);
    } catch (e) {
      if (id !== requestId.current) return;
      setLines([]);
      setHasEarlier(false);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [name]);

  useEffect(() => {
    void loadTail();
    return () => {
      requestId.current += 1; // drop an answer that arrives after the viewer closed or switched files
    };
  }, [loadTail]);

  const loadEarlier = async () => {
    const id = ++requestId.current;
    setLoadingEarlier(true);
    setError(null);
    try {
      const chunk = await fetchLogChunk(name, { end: start, lines: PAGE_LINES });
      if (id !== requestId.current) return;
      const el = scrollRef.current;
      pendingScroll.current = el ? { kind: "keep", height: el.scrollHeight, top: el.scrollTop } : null;
      setLines((prev) => [...chunk.lines, ...prev]);
      setStart(chunk.start);
      setHasEarlier(chunk.has_earlier);
    } catch (e) {
      if (id !== requestId.current) return;
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingEarlier(false);
    }
  };

  // After new lines are in the DOM: jump to the newest line, or keep the reader where they were
  // when older lines were added above.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    const action = pendingScroll.current;
    pendingScroll.current = null;
    if (!el || !action) return;
    if (action.kind === "bottom") el.scrollTop = el.scrollHeight;
    else el.scrollTop = action.top + (el.scrollHeight - action.height);
  }, [lines]);

  const entries = useMemo(() => classify(lines), [lines]);
  const counts = useMemo(() => {
    const totals: Record<Level, number> = { error: 0, warning: 0, info: 0 };
    for (const entry of entries) totals[entry.level] += 1;
    return totals;
  }, [entries]);

  const needle = query.trim().toLowerCase();
  const visible = useMemo(
    () => entries.filter((e) => shown[e.level] && (!needle || e.text.toLowerCase().includes(needle))),
    [entries, shown, needle],
  );
  const logLines: LogLine[] = useMemo(
    () =>
      visible.map((e, i) => ({
        jobId: name,
        // An empty div has no height, so keep blank lines visible.
        message: e.text === "" ? " " : e.text,
        level: LEVELS.find((l) => l.id === e.level)?.value ?? 20,
        ts: i,
      })),
    [visible, name],
  );

  const filtered = needle !== "" || LEVELS.some((l) => !shown[l.id]);

  const copyVisible = async () => {
    const text = visible.map((e) => e.text).join("\n");
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  const emptyMessage = loading
    ? "Loading…"
    : error
      ? "Could not read this log."
      : lines.length === 0
        ? "This log is empty."
        : "No lines match the filters.";

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div className="min-w-0 space-y-1.5">
          <CardTitle className="truncate font-mono text-base">{name}</CardTitle>
          <CardDescription>
            {loading
              ? "Loading…"
              : `${formatBytes(sizeBytes)} · ${lines.length} line${lines.length === 1 ? "" : "s"} loaded${
                  hasEarlier ? "" : " (start of file)"
                }`}
          </CardDescription>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void loadTail()}
            disabled={loading || loadingEarlier}
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            Refresh
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => void copyVisible()} disabled={visible.length === 0}>
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copied ? "Copied" : "Copy"}
          </Button>
          <Button
            type="button"
            variant={wrap ? "secondary" : "outline"}
            size="sm"
            aria-pressed={wrap}
            onClick={() => setWrap((prev) => !prev)}
            title="Wrap long lines"
          >
            <WrapText className="h-4 w-4" />
            Wrap
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onClose} aria-label="Close log viewer" title="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[12rem] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search this log…"
              aria-label="Search this log"
              className="h-8 pl-9 text-xs"
            />
          </div>
          {LEVELS.map((level) => (
            <Button
              key={level.id}
              type="button"
              size="sm"
              variant={shown[level.id] ? "secondary" : "outline"}
              aria-pressed={shown[level.id]}
              onClick={() => setShown((prev) => ({ ...prev, [level.id]: !prev[level.id] }))}
              className={cn(!shown[level.id] && "text-muted-foreground")}
            >
              <span className={cn("h-2 w-2 rounded-full", level.dot)} />
              {level.label}
              <span className="text-muted-foreground">{counts[level.id]}</span>
            </Button>
          ))}
        </div>

        {hasEarlier && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => void loadEarlier()}
            disabled={loading || loadingEarlier}
          >
            {loadingEarlier ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
            Load earlier lines
          </Button>
        )}

        <div ref={scrollRef} className="h-96 overflow-auto rounded-md border bg-muted/30 p-3">
          <LogStream logs={logLines} wrap={wrap} className="overflow-visible" emptyMessage={emptyMessage} />
        </div>

        <p className="text-xs text-muted-foreground">
          {filtered ? `${visible.length} of ${lines.length} loaded lines shown` : `${lines.length} lines`}
          {filtered && hasEarlier && " · filters only cover the loaded lines, load earlier lines to search further back"}
        </p>

        {error && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
