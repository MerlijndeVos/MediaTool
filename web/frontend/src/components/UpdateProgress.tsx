import { Progress } from "@/components/ui/progress";
import type { UpdateApplyStatus } from "@/api/client";

interface UpdateProgressProps {
  applyStatus: UpdateApplyStatus | null;
  applying: boolean;
}

export function UpdateProgress({ applyStatus, applying }: UpdateProgressProps) {
  if (!applying || !applyStatus) return null;

  const showBar = applyStatus.phase === "downloading" && applyStatus.progress > 0;

  return (
    <div className="space-y-2 rounded-lg border bg-muted/30 p-4">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="font-medium text-foreground">
          {applyStatus.phase === "downloading" ? "Downloading update" : "Installing update"}
        </span>
        {showBar && (
          <span className="shrink-0 text-muted-foreground">{Math.round(applyStatus.progress)}%</span>
        )}
      </div>
      {showBar && <Progress value={applyStatus.progress} />}
      {applyStatus.message && (
        <p className="text-sm text-muted-foreground">{applyStatus.message}</p>
      )}
      {applyStatus.phase === "installing" && (
        <p className="text-xs text-muted-foreground">
          A setup progress window should appear on Windows. Toolbox will reopen when installation
          finishes.
        </p>
      )}
    </div>
  );
}
