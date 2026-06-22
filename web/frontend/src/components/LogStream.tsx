import { useEffect, useRef, useState } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ActiveJob, LogLine } from "@/lib/types";

function UndoConfirmDialog({
  open,
  opCount,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  opCount: number;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    else if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      className="app-dialog z-50"
      onClose={() => onOpenChange(false)}
      onClick={(e) => {
        if (e.target === dialogRef.current) onOpenChange(false);
      }}
    >
      <div className="space-y-4 p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-300">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="space-y-1">
            <h2 className="text-lg font-semibold text-foreground">Undo rename?</h2>
            <p className="text-sm text-muted-foreground">
              This reverses {opCount} file operation{opCount === 1 ? "" : "s"} from the selected
              rename job — moved files go back, copies are deleted.
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={() => {
              onOpenChange(false);
              onConfirm();
            }}
          >
            Undo rename
          </Button>
        </div>
      </div>
    </dialog>
  );
}

export function LogStream({
  logs,
  className,
  wrap = false,
  emptyMessage = "Output from jobs will appear here…",
}: {
  logs: LogLine[];
  className?: string;
  wrap?: boolean;
  emptyMessage?: string;
}) {
  return (
    <pre
      className={cn(
        "cursor-text select-text overflow-auto font-mono text-xs leading-relaxed text-muted-foreground",
        wrap ? "whitespace-pre-wrap break-words" : "whitespace-pre",
        className,
      )}
    >
      {logs.length === 0 ? (
        <span className="text-muted-foreground/70">{emptyMessage}</span>
      ) : (
        logs.map((line, i) => (
          <div
            key={`${line.ts}-${i}`}
            className={cn(
              line.level >= 40 && "text-red-500 dark:text-red-400",
              line.level === 30 && "text-amber-600 dark:text-amber-400",
            )}
          >
            {line.message}
          </div>
        ))
      )}
    </pre>
  );
}

export function UndoRenameBar({
  jobs,
  onUndo,
  undoing = false,
}: {
  jobs: ActiveJob[];
  onUndo: (jobId: string) => void;
  undoing?: boolean;
}) {
  const [confirmJob, setConfirmJob] = useState<ActiveJob | null>(null);

  if (jobs.length === 0) return null;

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 border-b bg-amber-500/10 px-4 py-2">
        <span className="text-xs font-medium text-amber-950 dark:text-amber-100">Undo rename</span>
        {jobs.map((job) => (
          <Button
            key={job.id}
            type="button"
            size="sm"
            variant="outline"
            disabled={undoing}
            className="h-7 border-amber-500/40 bg-background/80 text-xs"
            onClick={() => setConfirmJob(job)}
          >
            <RotateCcw className="h-3 w-3" />
            {job.id.slice(0, 8)}
            {job.undo_op_count != null && (
              <span className="text-muted-foreground">({job.undo_op_count})</span>
            )}
          </Button>
        ))}
      </div>
      <UndoConfirmDialog
        open={confirmJob != null}
        opCount={confirmJob?.undo_op_count ?? 0}
        onOpenChange={(next) => {
          if (!next) setConfirmJob(null);
        }}
        onConfirm={() => {
          if (confirmJob) onUndo(confirmJob.id);
          setConfirmJob(null);
        }}
      />
    </>
  );
}
