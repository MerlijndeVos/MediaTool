import { Download, Loader2, RefreshCw } from "lucide-react";
import { UpdateProgress } from "@/components/UpdateProgress";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { UpdatesState } from "@/hooks/useUpdates";

export function UpdatesPanel({
  check,
  checking,
  networkError,
  applyStatus,
  applyError,
  applying,
  showUpdate,
  runCheck,
  setModalOpen,
}: UpdatesState) {
  const error = networkError ?? check?.error ?? applyError;
  const status = checking
    ? "Checking for updates…"
    : applyStatus?.phase === "error"
      ? applyStatus.error
      : check?.status_message;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Updates</CardTitle>
        <CardDescription>
          Check for new versions and install updates from GitHub releases.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="default"
            disabled={checking || applying}
            onClick={runCheck}
            className="gap-1.5"
          >
            {checking ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Check for updates
          </Button>
          {showUpdate && check?.latest_version && (
            <Button
              type="button"
              size="default"
              disabled={applying}
              onClick={() => setModalOpen(true)}
              className="min-w-[9.5rem] gap-1.5 whitespace-nowrap"
            >
              {applying ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {applyStatus?.phase === "installing" ? "Installing…" : "Downloading…"}
                </>
              ) : (
                <>
                  <Download className="h-4 w-4" />
                  Update to v{check.latest_version}
                </>
              )}
            </Button>
          )}
        </div>

        <UpdateProgress applyStatus={applyStatus} applying={applying} />

        {check && (
          <p className="text-sm text-muted-foreground">
            Installed version: <span className="font-medium text-foreground">v{check.current_version}</span>
            {check.latest_version && (
              <>
                {" "}
                — Latest release:{" "}
                <span className="font-medium text-foreground">v{check.latest_version}</span>
              </>
            )}
          </p>
        )}

        {error && (
          <p className={cn("text-sm", "text-red-600 dark:text-red-400")}>{error}</p>
        )}
        {!error && status && !applying && (
          <p className="text-sm text-muted-foreground">{status}</p>
        )}
      </CardContent>
    </Card>
  );
}
