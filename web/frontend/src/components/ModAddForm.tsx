import { useState } from "react";
import { File as FileIcon, FolderOpen, Search } from "lucide-react";
import { prepareModInstall } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isDesktopApp, pickFiles, pickFolder } from "@/lib/desktop";
import type { ModInstallPreview } from "@/lib/types";

interface ModAddFormProps {
  busy: boolean;
  onBusy: (busy: boolean) => void;
  onPrepared: (preview: ModInstallPreview) => void;
  onError: (message: string) => void;
}

/** Add a mod from a git address, or from a folder, zip, .py or (for a theme) .toml file. It only fetches and checks: the review comes next. */
export function ModAddForm({ busy, onBusy, onPrepared, onError }: ModAddFormProps) {
  const [location, setLocation] = useState("");
  const [ref, setRef] = useState("");
  const desktop = isDesktopApp();
  const isGit = /^https?:\/\//i.test(location.trim());

  const review = async (where: string) => {
    const target = where.trim();
    if (!target) return;
    onBusy(true);
    onError("");
    try {
      onPrepared(await prepareModInstall({ location: target, ref: isGit ? ref.trim() : "" }));
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      onBusy(false);
    }
  };

  const choose = async (kind: "folder" | "file") => {
    const path = kind === "folder" ? await pickFolder() : ((await pickFiles(false))[0] ?? null);
    if (path) {
      setLocation(path);
      void review(path);
    }
  };

  return (
    <form
      className="space-y-2 rounded-lg border border-border/60 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        void review(location);
      }}
    >
      <p className="text-sm font-medium">Add a mod</p>
      <p className="text-xs text-muted-foreground">
        Paste a git address (for example https://github.com/name/my-mod), or choose a folder, a
        .zip, a .py file or, for a theme, a single .toml file. You get to review it before anything
        is installed.
      </p>
      <div className="flex flex-wrap gap-2">
        <Input
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="https://github.com/name/my-mod  or  C:\path\to\mod"
          aria-label="Git address or path"
          className="min-w-0 flex-1 basis-64"
        />
        {isGit && (
          <Input
            value={ref}
            onChange={(e) => setRef(e.target.value)}
            placeholder="Tag, branch or commit (optional)"
            aria-label="Tag, branch or commit"
            className="basis-56"
          />
        )}
        <Button type="submit" size="sm" className="h-10" disabled={busy || !location.trim()}>
          <Search className="h-4 w-4" />
          Review
        </Button>
      </div>
      {desktop && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void choose("folder")}>
            <FolderOpen className="h-4 w-4" />
            Choose folder
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void choose("file")}>
            <FileIcon className="h-4 w-4" />
            Choose zip, .py or .toml file
          </Button>
        </div>
      )}
    </form>
  );
}
