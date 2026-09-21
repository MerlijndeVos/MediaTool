import { useState } from "react";
import { AlertTriangle, CheckCircle2, FolderOpen, Info, XCircle } from "lucide-react";
import { openJobResult } from "@/api/client";
import { MarkdownLite } from "@/components/MarkdownLite";
import { Button } from "@/components/ui/button";
import type { ModResult, ResultLevel } from "@/lib/types";
import { cn } from "@/lib/utils";

const LEVEL_STYLE: Record<ResultLevel, { box: string; icon: typeof Info }> = {
  info: { box: "border-border/60 bg-muted/40", icon: Info },
  success: { box: "border-success/40 bg-success/10", icon: CheckCircle2 },
  warning: { box: "border-warning/40 bg-warning/10", icon: AlertTriangle },
  error: { box: "border-danger/40 bg-danger/10", icon: XCircle },
};
const LEVEL_ICON_COLOR: Record<ResultLevel, string> = {
  info: "text-muted-foreground",
  success: "text-success-text",
  warning: "text-warning-text",
  error: "text-danger-text",
};

/** A column of numbers is right-aligned, header included. */
function numeric(result: Extract<ModResult, { view: "table" }>, column: number): boolean {
  return result.rows.length > 0 && result.rows.every((row) => typeof row[column] === "number");
}

function Title({ title }: { title: string }) {
  return title ? <h3 className="text-sm font-semibold">{title}</h3> : null;
}

function FileRow({
  path,
  label,
  jobId,
  onError,
}: {
  path: string;
  label?: string;
  jobId?: string;
  onError: (message: string) => void;
}) {
  const act = (reveal: boolean) =>
    jobId &&
    openJobResult(jobId, path, reveal).catch((e) => onError(e instanceof Error ? e.message : String(e)));
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-1.5">
      <div className="min-w-0 flex-1">
        <p className="break-all text-xs">{path}</p>
        {label && <p className="text-[11px] text-muted-foreground">{label}</p>}
      </div>
      {jobId && (
        <div className="flex shrink-0 gap-1.5">
          <Button type="button" variant="outline" size="sm" onClick={() => void act(false)}>
            Open
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            title="Show in its folder"
            onClick={() => void act(true)}
          >
            <FolderOpen className="h-3.5 w-3.5" />
            Show
          </Button>
        </div>
      )}
    </li>
  );
}

function ResultView({ result, jobId }: { result: ModResult; jobId?: string }) {
  const [fileError, setFileError] = useState<string | null>(null);

  switch (result.view) {
    case "table":
      return (
        <div className="space-y-1.5">
          <Title title={result.title} />
          <div className="max-h-96 overflow-auto rounded-md border border-border/60">
            <table className="w-full border-collapse text-left text-xs">
              <thead className="sticky top-0 bg-muted">
                <tr>
                  {result.columns.map((column, i) => (
                    <th key={i} className={cn("px-3 py-1.5 font-semibold", numeric(result, i) && "text-right")}>
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, r) => (
                  <tr key={r} className="border-t border-border/60">
                    {row.map((cell, c) => (
                      <td
                        key={c}
                        className={cn("px-3 py-1.5", numeric(result, c) && "text-right tabular-nums")}
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.truncated && (
            <p className="text-xs text-muted-foreground">Only the first {result.rows.length} rows are shown.</p>
          )}
        </div>
      );
    case "counters":
      return (
        <div className="space-y-1.5">
          <Title title={result.title} />
          <div className="grid grid-cols-[repeat(auto-fill,minmax(8rem,1fr))] gap-2">
            {result.items.map((item, i) => (
              <div key={i} className="rounded-lg border border-border/60 bg-muted/40 px-3 py-2">
                <p className="truncate text-base font-semibold tabular-nums">{item.value}</p>
                <p className="truncate text-[11px] text-muted-foreground">{item.label}</p>
              </div>
            ))}
          </div>
        </div>
      );
    case "files":
      return (
        <div className="space-y-1.5">
          <Title title={result.title} />
          <ul className="max-h-96 divide-y divide-border/60 overflow-auto rounded-md border border-border/60 px-3">
            {result.files.map((file, i) => (
              <FileRow key={i} path={file.path} label={file.label} jobId={jobId} onError={setFileError} />
            ))}
          </ul>
          {result.truncated && (
            <p className="text-xs text-muted-foreground">Only the first {result.files.length} files are listed.</p>
          )}
          {fileError && <p className="text-xs text-danger-text">{fileError}</p>}
        </div>
      );
    case "markdown":
      return (
        <div className="space-y-1.5">
          <Title title={result.title} />
          <div className="rounded-md border border-border/60 bg-muted/30 p-3">
            <MarkdownLite text={result.text} />
          </div>
        </div>
      );
    case "image":
      // The server only ever sends a data: URI for a real picture; anything else is not drawn.
      return /^data:image\/(png|jpeg|gif|webp);base64,/.test(result.src) ? (
        <div className="space-y-1.5">
          <Title title={result.title} />
          <img src={result.src} alt={result.alt} className="max-h-96 max-w-full rounded-md border border-border/60" />
        </div>
      ) : null;
    case "message": {
      const { box, icon: Icon } = LEVEL_STYLE[result.level] ?? LEVEL_STYLE.info;
      return (
        <div className={cn("flex items-start gap-2 rounded-lg border px-3 py-2 text-sm", box)} role="status">
          <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", LEVEL_ICON_COLOR[result.level] ?? LEVEL_ICON_COLOR.info)} />
          <p className="min-w-0 break-words">{result.text}</p>
        </div>
      );
    }
    default:
      return null;
  }
}

/** What a mod showed after a run (or an action): tables, counters, file lists, notes and pictures. */
export function ModResults({ results, jobId }: { results: ModResult[]; jobId?: string }) {
  if (results.length === 0) return null;
  return (
    <div className="space-y-4">
      {results.map((result, i) => (
        <ResultView key={i} result={result} jobId={jobId} />
      ))}
    </div>
  );
}
