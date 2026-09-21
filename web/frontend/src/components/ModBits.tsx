import { useState } from "react";
import { AlertTriangle, Check, Copy, ShieldCheck } from "lucide-react";
import { Button, type ButtonProps } from "@/components/ui/button";
import { copyText } from "@/lib/clipboard";
import type { ModSourceFile } from "@/lib/types";

export interface Access {
  network: boolean;
  writes_files: boolean;
  runs_programs: boolean;
}

export function PermissionChips({ permissions }: { permissions: Access | null }) {
  if (!permissions) {
    return <span className="text-xs text-muted-foreground">Does not say what it needs</span>;
  }
  const chips = [
    permissions.network && "Uses the network",
    permissions.writes_files && "Writes files",
    permissions.runs_programs && "Runs programs",
  ].filter(Boolean) as string[];
  if (chips.length === 0) {
    return <span className="text-xs text-muted-foreground">Declares no special access</span>;
  }
  return (
    <span className="flex flex-wrap gap-1.5">
      {chips.map((chip) => (
        <span
          key={chip}
          className="rounded-full bg-warning/15 px-2 py-0.5 text-[11px] font-medium text-warning-text"
        >
          {chip}
        </span>
      ))}
    </span>
  );
}

/** Where a tool appears in the menu, or that a mod is a theme. Shown before and after installing. */
export function PlacementChip({
  type,
  group,
  newSection = false,
}: {
  type: "tool" | "theme";
  group?: string;
  newSection?: boolean;
}) {
  const text =
    type === "theme" ? "Theme" : `Appears in ${group || "Other"}${newSection ? " (a new section)" : ""}`;
  return (
    <span
      className="inline-block rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
      title={type === "theme" ? "Changes colours and styling. No code runs." : "The menu section this tool is in"}
    >
      {text}
    </span>
  );
}

/** What replaces the code warning for a theme: it is data, and there is nothing to run. */
export function ThemeNotice() {
  return (
    <div className="flex gap-3 rounded-lg border border-success/40 bg-success/10 p-3 text-xs text-muted-foreground">
      <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-success-text" />
      <p>
        This only changes colours and settings. No code runs. It is checked before it is used: a
        theme that would make warnings or the Remove button hard to read is refused.
      </p>
    </div>
  );
}

export function TrustNotice({ children }: { children?: React.ReactNode }) {
  return (
    <div className="flex gap-3 rounded-lg border border-danger/30 bg-danger/5 p-3 text-xs text-muted-foreground">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-danger-text" />
      <p>
        {children ?? (
          <>
            A mod is code that runs with the same access as Toolbox: it can read, change and delete
            your files. The access a mod declares is only a description, it is not enforced, and
            Toolbox does not review mods. Only use mods from people you trust, and read the code
            first.
          </>
        )}
      </p>
    </div>
  );
}

/** A button that copies text (fetched lazily) and says so for a moment. */
export function CopyButton({
  getText,
  children,
  onFailed,
  ...props
}: Omit<ButtonProps, "onClick"> & {
  getText: () => string | Promise<string>;
  onFailed?: (message: string) => void;
}) {
  const [done, setDone] = useState(false);
  const handle = async () => {
    try {
      const ok = await copyText(await getText());
      if (!ok) throw new Error("The clipboard is not available.");
      setDone(true);
      window.setTimeout(() => setDone(false), 2000);
    } catch (e) {
      onFailed?.(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <Button type="button" variant="outline" size="sm" onClick={() => void handle()} {...props}>
      {done ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      {done ? "Copied" : children}
    </Button>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(bytes < 10240 ? 1 : 0)} KB`;
}

/** Every file of a mod, each readable in place. */
export function CodeFiles({ files }: { files: ModSourceFile[] }) {
  return (
    <div className="space-y-1.5">
      {files.map((file) => (
        <details key={file.path} className="rounded-md border border-border/60 bg-background">
          <summary className="flex cursor-pointer items-center justify-between gap-3 px-3 py-1.5 text-xs">
            <span className="min-w-0 break-all font-medium">{file.path}</span>
            <span className="shrink-0 text-muted-foreground">{formatSize(file.size)}</span>
          </summary>
          {file.text === null ? (
            <p className="border-t border-border/60 px-3 py-2 text-xs text-muted-foreground">
              Not shown ({file.size === 0 ? "empty" : "binary or too large"}).
            </p>
          ) : (
            <pre className="max-h-80 overflow-auto border-t border-border/60 p-3 text-[11px] leading-snug">
              {file.text}
              {file.truncated ? "\n… (cut off)" : ""}
            </pre>
          )}
        </details>
      ))}
    </div>
  );
}

/** The review prompt followed by every file, ready to paste into an AI assistant. */
export function reviewPromptWithCode(prompt: string, files: ModSourceFile[]): string {
  const marker = prompt.lastIndexOf("<PASTE");
  const head = marker === -1 ? prompt : prompt.slice(0, marker).trimEnd();
  const body = files
    .filter((f) => f.text !== null)
    .map((f) => `### ${f.path}\n\`\`\`\n${f.text}\n\`\`\``)
    .join("\n\n");
  return `${head}\n\n${body}\n`;
}
