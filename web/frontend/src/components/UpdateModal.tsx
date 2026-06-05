import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Download, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ReleaseNotes } from "@/components/ReleaseNotes";

interface UpdateModalProps {
  open: boolean;
  currentVersion: string;
  latestVersion: string;
  releaseNotes?: string | null;
  releaseUrl?: string | null;
  applying: boolean;
  applyMessage?: string | null;
  onSkip: () => void;
  onUpdate: () => void;
}

export function UpdateModal({
  open,
  currentVersion,
  latestVersion,
  releaseNotes,
  releaseUrl,
  applying,
  applyMessage,
  onSkip,
  onUpdate,
}: UpdateModalProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!open || !mounted) return null;

  const notes = releaseNotes?.trim();

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !applying) onSkip();
      }}
    >
      <Card
        role="dialog"
        aria-modal="true"
        aria-labelledby="update-modal-title"
        aria-describedby="update-modal-description"
        className="flex max-h-[min(calc(100vh-2rem),640px)] w-full max-w-lg flex-col shadow-xl"
      >
        <CardHeader className="shrink-0 border-b pb-4">
          <div className="flex items-start gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <Sparkles className="h-5 w-5" />
            </div>
            <div className="min-w-0 space-y-1">
              <CardTitle id="update-modal-title">Update available</CardTitle>
              <CardDescription id="update-modal-description">
                Media Tool v{latestVersion} is ready to install. You&apos;re on v{currentVersion}.
              </CardDescription>
            </div>
          </div>
        </CardHeader>

        <CardContent className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden pt-4">
          {notes ? (
            <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border bg-muted/30 p-4">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                What&apos;s new
              </p>
              <ReleaseNotes text={notes} />
              {releaseUrl && (
                <a
                  href={releaseUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-4 inline-block text-sm text-primary hover:underline"
                >
                  View full release on GitHub
                </a>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              A new version is available with improvements and fixes.
              {releaseUrl && (
                <>
                  {" "}
                  <a
                    href={releaseUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary hover:underline"
                  >
                    View release notes
                  </a>
                </>
              )}
            </p>
          )}

          <div className="flex shrink-0 items-center justify-end gap-2 border-t pt-4">
            <Button type="button" variant="outline" size="default" disabled={applying} onClick={onSkip}>
              Skip for now
            </Button>
            <Button type="button" size="default" disabled={applying} onClick={onUpdate} className="gap-1.5">
              {applying ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {applyMessage || "Updating…"}
                </>
              ) : (
                <>
                  <Download className="h-4 w-4" />
                  Update to v{latestVersion}
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>,
    document.body,
  );
}
