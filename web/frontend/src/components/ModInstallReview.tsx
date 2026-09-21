import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { fetchModPrompts } from "@/api/client";
import { Button } from "@/components/ui/button";
import { CheckField } from "@/components/fields";
import { CodeFiles, CopyButton, PermissionChips, TrustNotice, reviewPromptWithCode } from "@/components/ModBits";
import type { ModInstallMeta, ModInstallPreview } from "@/lib/types";

export function describeSource(source: ModInstallMeta): string {
  switch (source.type) {
    case "git":
      return (source.url ?? "") + (source.subdir ? `  (folder ${source.subdir})` : "");
    case "folder":
      return `Folder ${source.path ?? ""}`;
    case "zip":
      return `Zip file ${source.path ?? ""}`;
    case "file":
      return `File ${source.path ?? ""}`;
  }
}

const CHANGE_LABEL = { added: "added", removed: "removed", changed: "changed" } as const;

interface ModInstallReviewProps {
  preview: ModInstallPreview;
  busy: boolean;
  onConfirm: (enable: boolean) => void;
  onCancel: () => void;
  onError: (message: string) => void;
}

/** The trust prompt: everything about a mod that has been downloaded and checked but not run. */
export function ModInstallReview({ preview, busy, onConfirm, onCancel, onError }: ModInstallReviewProps) {
  const { manifest, source } = preview;
  const updating = preview.replaces !== null;
  const [enable, setEnable] = useState(true);

  return (
    <div className="space-y-4 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
      <div>
        <h3 className="text-sm font-semibold">
          {updating
            ? `Update ${manifest.name}? ${preview.replaces?.version} → ${manifest.version}`
            : `Install ${manifest.name}?`}
        </h3>
        <p className="text-xs text-muted-foreground">
          It has been downloaded and checked, but nothing has run. Nothing is installed until you
          say so.
        </p>
      </div>

      <dl className="grid gap-x-4 gap-y-1.5 text-xs sm:grid-cols-[7rem_1fr]">
        <dt className="text-muted-foreground">Name</dt>
        <dd>
          <span className="font-medium">{manifest.name}</span> v{manifest.version}{" "}
          <span className="text-muted-foreground">(id: {manifest.id})</span>
        </dd>
        {manifest.description && (
          <>
            <dt className="text-muted-foreground">What it says</dt>
            <dd>{manifest.description}</dd>
          </>
        )}
        <dt className="text-muted-foreground">Author</dt>
        <dd>{manifest.author || "Not stated"}</dd>
        <dt className="text-muted-foreground">Comes from</dt>
        <dd className="break-all">{describeSource(source)}</dd>
        {source.type === "git" && (
          <>
            <dt className="text-muted-foreground">Exact commit</dt>
            <dd>
              <code className="break-all rounded bg-muted px-1">{source.commit}</code>
              <span className="ml-2 text-muted-foreground">
                pinned{source.ref ? `, from ${source.ref}` : ""}
              </span>
            </dd>
          </>
        )}
        <dt className="text-muted-foreground">Says it needs</dt>
        <dd className="space-y-1">
          <PermissionChips permissions={manifest.permissions} />
          <p className="text-muted-foreground">
            This is what the author declares. It is not enforced: the code can do anything you can.
          </p>
        </dd>
      </dl>

      {preview.warnings.length > 0 && (
        <ul className="list-disc space-y-1 rounded-md border border-red-500/30 bg-red-500/5 py-2 pl-7 pr-3 text-xs">
          {preview.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      {updating && preview.changes && (
        <div className="space-y-1 text-xs">
          <p className="font-medium">
            What changed since {preview.replaces?.commit ? preview.replaces.commit.slice(0, 10) : "the installed version"}
            {preview.compare_url && (
              <a
                href={preview.compare_url}
                target="_blank"
                rel="noreferrer"
                className="ml-2 inline-flex items-center gap-1 font-normal text-primary underline-offset-2 hover:underline"
              >
                Compare on GitHub <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </p>
          {preview.changes.length === 0 ? (
            <p className="text-muted-foreground">No files differ.</p>
          ) : (
            <ul className="space-y-0.5">
              {preview.changes.map((c) => (
                <li key={c.path}>
                  <span className="inline-block w-16 text-muted-foreground">{CHANGE_LABEL[c.status]}</span>
                  {c.path}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <details className="text-xs">
        <summary className="cursor-pointer font-medium">
          Read the code ({preview.files.length} {preview.files.length === 1 ? "file" : "files"})
        </summary>
        <div className="mt-2 space-y-2">
          <CodeFiles files={preview.files} />
          <CopyButton
            onFailed={onError}
            getText={async () => reviewPromptWithCode((await fetchModPrompts()).review, preview.files)}
          >
            Copy review prompt with the code
          </CopyButton>
          <p className="text-muted-foreground">
            Paste it into an AI assistant to have the code explained in plain language. AI can be
            wrong; it is a second opinion, not a guarantee.
          </p>
        </div>
      </details>

      <TrustNotice />

      {!updating && (
        <CheckField label="Turn it on after installing" checked={enable} onChange={setEnable} />
      )}

      <div className="flex gap-2">
        <Button type="button" variant="outline" size="sm" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
        <Button type="button" size="sm" disabled={busy} onClick={() => onConfirm(enable)}>
          {updating ? "Update" : "Install"}
        </Button>
      </div>
    </div>
  );
}
