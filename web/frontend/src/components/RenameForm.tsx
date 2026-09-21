import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Pencil, Plus, Save, Trash2 } from "lucide-react";
import { deleteRenameProfile, fetchRenameProfiles, saveRenameProfile } from "@/api/client";
import { CheckField, PathField, SelectField, ToolRunActions } from "@/components/fields";
import { ProfileEditor } from "@/components/ProfileEditor";
import { Button } from "@/components/ui/button";
import {
  emptyProfile,
  profilesEqual,
  type RenameMode,
  type RenameProfile,
} from "@/lib/renameProfiles";
import { cn, normalizeFilePath } from "@/lib/utils";

const STANDARD_ID = "builtin:standard";
const TIDY_ID = "builtin:tidy";

function RenameFormatInfo() {
  return (
    <details className="group rounded-lg border bg-muted/30 text-sm open:bg-muted/40">
      <summary className="cursor-pointer select-none px-4 py-3 font-medium text-foreground marker:content-none [&::-webkit-details-marker]:hidden">
        <span className="inline-flex items-center gap-2">
          Supported filename formats
          <span className="text-xs font-normal text-muted-foreground group-open:hidden">(click to expand)</span>
        </span>
      </summary>
      <div className="space-y-4 border-t px-4 py-3 text-muted-foreground">
        <div>
          <p className="mb-1.5 font-medium text-foreground">TV episodes</p>
          <ul className="list-inside list-disc space-y-1 text-xs leading-relaxed">
            <li>
              Standard codes: <code className="rounded bg-muted px-1">S01E01</code>,{" "}
              <code className="rounded bg-muted px-1">1x01</code>,{" "}
              <code className="rounded bg-muted px-1">Season 1 Episode 5</code> (dots, dashes, and
              underscores are normalized)
            </li>
            <li>
              Double episodes: <code className="rounded bg-muted px-1">S01E01-E02</code>,{" "}
              <code className="rounded bg-muted px-1">S01E01&amp;E02</code>,{" "}
              <code className="rounded bg-muted px-1">1x01x02</code>
            </li>
            <li>
              Episode titles after the code:{" "}
              <code className="rounded bg-muted px-1">Breaking Bad S01E01 Pilot</code>
            </li>
            <li>
              Bare episode numbers (season 1):{" "}
              <code className="rounded bg-muted px-1">Show Name 47 Episode Title</code>
            </li>
          </ul>
        </div>
        <div>
          <p className="mb-1.5 font-medium text-foreground">Movies</p>
          <ul className="list-inside list-disc space-y-1 text-xs leading-relaxed">
            <li>
              Requires a year (19xx or 20xx):{" "}
              <code className="rounded bg-muted px-1">Movie Name 2008</code> or{" "}
              <code className="rounded bg-muted px-1">Movie Name (2008)</code>
            </li>
            <li>Release tags after the year are ignored; the year must be near the end of the name</li>
          </ul>
        </div>
        <div>
          <p className="mb-1.5 font-medium text-foreground">Cleaned automatically</p>
          <p className="text-xs leading-relaxed">
            Bracket tags like <code className="rounded bg-muted px-1">[RARBG]</code>, quality/source
            tokens (<code className="rounded bg-muted px-1">1080p</code>,{" "}
            <code className="rounded bg-muted px-1">WEB-DL</code>,{" "}
            <code className="rounded bg-muted px-1">x265</code>), and scene groups are stripped from
            titles. Subtitle language tags (<code className="rounded bg-muted px-1">.en</code>,{" "}
            <code className="rounded bg-muted px-1">.forced</code>) are kept.
          </p>
        </div>
        <div>
          <p className="mb-1.5 font-medium text-foreground">Output layout</p>
          <ul className="list-inside list-disc space-y-1 text-xs leading-relaxed">
            <li>
              TV: <code className="rounded bg-muted px-1">Show Name/Season 01/Show Name - S01E01 - Title.mkv</code>
            </li>
            <li>
              Movie: <code className="rounded bg-muted px-1">Movie Name (2008)/Movie Name (2008).mkv</code>
            </li>
          </ul>
        </div>
      </div>
    </details>
  );
}

const RENAME_TYPE_OPTS = [
  { value: "auto", label: "Auto" },
  { value: "tv", label: "TV" },
  { value: "movie", label: "Movie" },
];

const RENAME_TARGET_OPTS = [
  { value: "folders", label: "Folders" },
  { value: "files", label: "Files" },
  { value: "both", label: "Folders and files" },
];

const RENAME_DEPTH_OPTS = [
  { value: "1", label: "Only directly inside" },
  { value: "2", label: "2 levels deep" },
  { value: "3", label: "3 levels deep" },
  { value: "50", label: "All levels" },
];

const MODES: { value: RenameMode; label: string; hint: string }[] = [
  { value: "media", label: "Shows & movies", hint: "Organize TV episodes, movies and subtitles" },
  { value: "generic", label: "Other", hint: "Clean up any folder or file names" },
];

/** A folder path compared loosely: no quotes, no trailing slash, and Windows paths ignore case. */
const samePath = (a: string, b: string) => {
  const clean = (p: string) => normalizeFilePath(p).replace(/[\\/]+$/, "");
  return clean(a).toLowerCase() === clean(b).toLowerCase();
};

/** A finished rename that renamed the folder the user had selected (or its undo). */
export interface RenamedRoot {
  from: string;
  to: string;
  jobId: string;
  undone: boolean;
}

interface RenameFormProps {
  onRun: (p: Record<string, unknown>) => void;
  disabled?: boolean;
  renamedRoot?: RenamedRoot;
}

export function RenameForm({ onRun, disabled, renamedRoot }: RenameFormProps) {
  const [mode, setMode] = useState<RenameMode>("media");
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [mediaType, setMediaType] = useState("auto");
  const [copy, setCopy] = useState(false);
  const [layout, setLayout] = useState(true);
  const [targets, setTargets] = useState("folders");
  const [maxDepth, setMaxDepth] = useState("1");
  const [includeRoot, setIncludeRoot] = useState(false);

  // When the rename changed the name of the chosen folder, the field follows it (and goes back on undo),
  // so the next preview does not point at a folder that no longer exists.
  const seenRoot = useRef<string | null>(null);
  useEffect(() => {
    if (!renamedRoot) return;
    const key = `${renamedRoot.jobId}:${renamedRoot.undone}`;
    if (seenRoot.current === key) return;
    seenRoot.current = key;
    setInput((current) => {
      if (!renamedRoot.undone && samePath(current, renamedRoot.from)) return renamedRoot.to;
      if (renamedRoot.undone && samePath(current, renamedRoot.to)) return renamedRoot.from;
      return current;
    });
  }, [renamedRoot]);

  // The selected folder is a folder, so it can only be renamed when folders are renamed.
  const rootPossible = targets !== "files";

  const [profiles, setProfiles] = useState<RenameProfile[]>([]);
  const [draft, setDraft] = useState<RenameProfile>(() => emptyProfile());
  const [editing, setEditing] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const loadProfiles = useCallback(async (selectId?: string) => {
    try {
      const { profiles: list } = await fetchRenameProfiles();
      setProfiles(list);
      const pick = list.find((p) => p.id === (selectId ?? STANDARD_ID)) ?? list[0];
      if (pick) setDraft(structuredClone(pick));
      setProfileError(null);
    } catch (e) {
      setProfileError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void loadProfiles();
  }, [loadProfiles]);

  const saved = useMemo(() => profiles.find((p) => p.id === draft.id), [profiles, draft.id]);
  const dirty = !saved || !profilesEqual(saved, draft);
  const canDelete = Boolean(saved && !saved.builtin);

  // Untouched built-in profiles follow the mode: Standard for shows, Tidy names for folders.
  const changeMode = (next: RenameMode) => {
    setMode(next);
    if (saved?.builtin && !dirty) {
      const target = profiles.find((p) => p.id === (next === "generic" ? TIDY_ID : STANDARD_ID));
      if (target) setDraft(structuredClone(target));
    }
  };

  const profileOptions = [
    ...profiles.map((p) => ({ value: p.id ?? "", label: p.builtin ? `${p.name} (built-in)` : p.name })),
    ...(draft.id ? [] : [{ value: "__draft__", label: `${draft.name || "Unsaved profile"} (unsaved)` }]),
  ];

  const selectProfile = (id: string) => {
    if (id === "__draft__") return;
    const found = profiles.find((p) => p.id === id);
    if (found) {
      setDraft(structuredClone(found));
      setProfileError(null);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setProfileError(null);
    try {
      let toSave = draft;
      if (draft.builtin) {
        // Built-ins are read-only: keep the edits as a new profile.
        const taken = new Set(profiles.map((p) => p.name.toLowerCase()));
        let name = draft.name;
        if (taken.has(name.toLowerCase())) name = `${name} (custom)`;
        toSave = { ...draft, id: undefined, builtin: false, name };
      }
      const result = await saveRenameProfile(toSave);
      await loadProfiles(result.id);
    } catch (e) {
      setProfileError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!saved?.id) return;
    setSaving(true);
    try {
      await deleteRenameProfile(saved.id);
      await loadProfiles();
      setEditing(false);
    } catch (e) {
      setProfileError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const runParams = (apply: boolean) =>
    mode === "media"
      ? {
          input,
          output: output || null,
          apply,
          copy,
          undo: false,
          type: mediaType,
          prune_empty_dirs: false,
          no_titlecase: false,
          strip_words: [],
          bare_episode_numbers: false,
          mode: "media",
          layout,
          profile: draft,
        }
      : {
          input,
          apply,
          mode: "generic",
          targets,
          max_depth: Number(maxDepth),
          include_root: includeRoot && rootPossible,
          profile: draft,
        };

  // What the AI may read when it suggests a profile from the names in the chosen folder.
  const folderScope =
    mode === "generic" && input.trim()
      ? {
          folder: input,
          targets,
          maxDepth: Number(maxDepth),
          includeRoot: includeRoot && rootPossible,
        }
      : undefined;

  return (
    <div className="space-y-4">
      <div role="tablist" aria-label="Rename mode" className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1">
        {MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            role="tab"
            aria-selected={mode === m.value}
            onClick={() => changeMode(m.value)}
            className={cn(
              "rounded-md px-3 py-2 text-left transition-colors",
              mode === m.value ? "bg-card shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <span className="block text-sm font-medium">{m.label}</span>
            <span className="block text-xs text-muted-foreground">{m.hint}</span>
          </button>
        ))}
      </div>

      {mode === "media" ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <PathField
              label="Input folder"
              value={input}
              onChange={setInput}
              tooltip="Media library root scanned recursively for TV shows, movies, and subtitles."
            />
            <PathField
              label="Output folder"
              value={output}
              onChange={setOutput}
              hint="Leave empty to reorganize in place."
              tooltip="Destination for the organized layout. Omit to reorganize under the input folder."
            />
          </div>
          <SelectField
            label="Media type"
            value={mediaType}
            onChange={setMediaType}
            tooltip="Auto detects TV (SxxExx or bare episode numbers) and movies (with a year). TV or Movie skips the other type."
            options={RENAME_TYPE_OPTS}
          />
          <RenameFormatInfo />
          <div className="grid gap-3 sm:grid-cols-2">
            <CheckField
              label="Organize into Show / Season folders"
              checked={layout}
              onChange={setLayout}
              tooltip="On: files move into Show Name/Season 01/. Off: files are only renamed and stay in their current folder."
            />
            <CheckField
              label="Copy instead of move"
              checked={copy}
              onChange={setCopy}
              tooltip="Copy files into the new layout and keep the originals."
            />
          </div>
        </>
      ) : (
        <>
          <PathField
            label="Folder"
            value={input}
            onChange={setInput}
            tooltip="The folder whose contents are renamed in place. Nothing is moved."
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField
              label="Rename"
              value={targets}
              onChange={setTargets}
              tooltip="Which entries inside the folder get renamed. Extensions are always kept."
              options={RENAME_TARGET_OPTS}
            />
            <SelectField
              label="How deep"
              value={maxDepth}
              onChange={setMaxDepth}
              tooltip="How many folder levels below the chosen folder are included."
              options={RENAME_DEPTH_OPTS}
            />
          </div>
          <CheckField
            label="Also rename the selected folder itself"
            checked={includeRoot && rootPossible}
            onChange={setIncludeRoot}
            disabled={!rootPossible}
            hint={
              rootPossible
                ? "It is renamed last, after everything inside it, and the folder field then follows its new name."
                : "Choose Folders, or Folders and files, to rename the selected folder as well."
            }
            tooltip="For the selected folder, {parent} is the folder it sits in and {n} is 1. A drive (C:\) can't be renamed. If another folder next to it already has the new name, a number is added. Undo puts the name back."
          />
        </>
      )}

      {/* Format profile */}
      <div className="space-y-3 rounded-lg border p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[12rem] flex-1">
            <SelectField
              label="Format profile"
              value={draft.id ?? "__draft__"}
              onChange={selectProfile}
              tooltip="Cleanup rules and output patterns used for renaming. Create your own, or let the AI build one from an example."
              options={profileOptions}
            />
          </div>
          <div className="flex flex-wrap gap-2 pb-0.5">
            <Button type="button" variant={editing ? "secondary" : "outline"} onClick={() => setEditing((v) => !v)}>
              <Pencil className="h-4 w-4" />
              {editing ? "Hide editor" : "Edit"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setDraft(emptyProfile());
                setEditing(true);
              }}
            >
              <Plus className="h-4 w-4" />
              New
            </Button>
            {dirty && (
              <Button type="button" onClick={() => void handleSave()} disabled={saving || !draft.name.trim()}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                {draft.builtin ? "Save as copy" : "Save"}
              </Button>
            )}
            {canDelete && (
              <Button
                type="button"
                variant="ghost"
                className="hover:text-destructive"
                onClick={() => void handleDelete()}
                disabled={saving}
                aria-label="Delete profile"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
        {dirty && !editing && (
          <p className="text-xs text-muted-foreground">
            This profile has unsaved changes. They are used for this run; save to keep them.
          </p>
        )}
        {profileError && (
          <p className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-700 dark:text-red-300">
            {profileError}
          </p>
        )}
        {editing && <ProfileEditor mode={mode} profile={draft} onChange={setDraft} folderScope={folderScope} />}
      </div>

      <ToolRunActions
        loading={disabled}
        disabled={disabled || !input}
        applyHint={
          mode === "generic"
            ? "Renames folders/files in place. You can undo the last apply from the log panel."
            : undefined
        }
        onPreview={() => onRun(runParams(false))}
        onApply={() => onRun(runParams(true))}
      />
    </div>
  );
}
