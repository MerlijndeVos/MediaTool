import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, FileVideo, FolderOpen, Plus, Trash2 } from "lucide-react";
import { Field } from "@/components/fields";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isDesktopApp, pickFiles } from "@/lib/desktop";
import { cn, fileExtension, normalizeFilePath } from "@/lib/utils";

export type FileListItem = { id: string; path: string };

function newId(): string {
  return crypto.randomUUID();
}

function fileName(path: string): string {
  const normalized = normalizeFilePath(path).replace(/\\/g, "/");
  const parts = normalized.split("/");
  return parts[parts.length - 1] || path;
}

function moveItem(items: FileListItem[], id: string, direction: -1 | 1): FileListItem[] {
  const index = items.findIndex((item) => item.id === id);
  if (index < 0) return items;
  const target = index + direction;
  if (target < 0 || target >= items.length) return items;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export function OrderedFileList({
  label,
  tooltip,
  items,
  onChange,
  showFormat = false,
  emptyMessage = "No files added yet. Add videos in the order they should be joined.",
}: {
  label: string;
  tooltip?: string;
  items: FileListItem[];
  onChange: (items: FileListItem[]) => void;
  showFormat?: boolean;
  emptyMessage?: string;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [manualPath, setManualPath] = useState("");
  const [picking, setPicking] = useState(false);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const showBrowse = isDesktopApp();

  const allSelected = items.length > 0 && selected.size === items.length;
  const someSelected = selected.size > 0 && !allSelected;

  useEffect(() => {
    const valid = new Set(items.map((item) => item.id));
    setSelected((prev) => {
      const next = new Set([...prev].filter((id) => valid.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [items]);

  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = someSelected;
  }, [someSelected]);

  const toggleSelectAll = () => {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(items.map((item) => item.id)));
  };

  const addPaths = (paths: string[]) => {
    const existing = new Set(items.map((item) => item.path));
    const added = paths
      .map((path) => normalizeFilePath(path))
      .filter((path) => path && !existing.has(path))
      .map((path) => ({ id: newId(), path }));
    if (added.length) onChange([...items, ...added]);
  };

  const handleBrowse = async () => {
    setPicking(true);
    try {
      addPaths(await pickFiles(true));
    } finally {
      setPicking(false);
    }
  };

  const handleManualAdd = () => {
    if (!manualPath.trim()) return;
    addPaths([manualPath]);
    setManualPath("");
  };

  const toggleSelected = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const removeSelected = () => {
    if (!selected.size) return;
    onChange(items.filter((item) => !selected.has(item.id)));
    setSelected(new Set());
  };

  const removeOne = (id: string) => {
    onChange(items.filter((item) => item.id !== id));
    setSelected((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  return (
    <Field label={label} tooltip={tooltip}>
      <div className="overflow-hidden rounded-md border border-input bg-background">
        {items.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-muted-foreground">{emptyMessage}</p>
        ) : (
          <ul className="divide-y divide-border">
            <li className="flex items-center gap-2 bg-muted/40 py-1.5 pl-3.5 pr-2">
              <input
                ref={selectAllRef}
                type="checkbox"
                checked={allSelected}
                onChange={toggleSelectAll}
                className="h-4 w-4 shrink-0 rounded border-input text-primary focus:ring-ring"
                aria-label="Select all files"
              />
              <button
                type="button"
                className="text-xs font-medium text-muted-foreground hover:text-foreground"
                onClick={toggleSelectAll}
              >
                {allSelected ? "Deselect all" : "Select all"}
                {someSelected ? ` (${selected.size} selected)` : ""}
              </button>
            </li>
            {items.map((item, index) => {
              const isSelected = selected.has(item.id);
              const ext = fileExtension(item.path);
              return (
                <li
                  key={item.id}
                  className={cn(
                    "flex items-center gap-2 py-2 pl-3.5 pr-2 transition-colors",
                    isSelected && "bg-primary/10",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelected(item.id)}
                    className="h-4 w-4 shrink-0 rounded border-input text-primary focus:ring-ring"
                    aria-label={`Select ${fileName(item.path)}`}
                  />
                  <span className="w-5 shrink-0 text-center text-xs font-medium text-muted-foreground">
                    {index + 1}
                  </span>
                  <FileVideo className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-2 truncate text-left text-sm hover:underline"
                    title={item.path}
                    onClick={() => toggleSelected(item.id)}
                  >
                    <span className="truncate">{fileName(item.path)}</span>
                    {showFormat && ext && (
                      <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                        {ext}
                      </span>
                    )}
                  </button>
                  <div className="flex shrink-0 items-center gap-0.5">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      disabled={index === 0}
                      aria-label="Move up"
                      onClick={() => onChange(moveItem(items, item.id, -1))}
                    >
                      <ArrowUp className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      disabled={index === items.length - 1}
                      aria-label="Move down"
                      onClick={() => onChange(moveItem(items, item.id, 1))}
                    >
                      <ArrowDown className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive"
                      aria-label="Remove"
                      onClick={() => removeOne(item.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <div className="flex flex-wrap items-center gap-2 border-t border-border bg-muted/30 px-2.5 py-2">
          {showBrowse ? (
            <Button
              type="button"
              variant="outline"
              className="h-10 shrink-0"
              disabled={picking}
              onClick={() => void handleBrowse()}
            >
              <FolderOpen className="h-4 w-4" />
              Add files
            </Button>
          ) : (
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <Input
                value={manualPath}
                onChange={(e) => setManualPath(e.target.value)}
                placeholder="C:\\path\\to\\part.mp4"
                className="min-w-0 flex-1"
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleManualAdd();
                }}
              />
              <Button
                type="button"
                variant="outline"
                className="h-10 shrink-0"
                disabled={!manualPath.trim()}
                onClick={handleManualAdd}
              >
                <Plus className="h-4 w-4" />
                Add
              </Button>
            </div>
          )}
          {showBrowse && (
            <div className="flex min-w-0 flex-1 items-center gap-2 sm:max-w-md">
              <Input
                value={manualPath}
                onChange={(e) => setManualPath(e.target.value)}
                placeholder="Or paste a path…"
                className="min-w-0 flex-1"
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleManualAdd();
                }}
              />
              <Button
                type="button"
                variant="outline"
                className="h-10 w-10 shrink-0 px-0"
                disabled={!manualPath.trim()}
                onClick={handleManualAdd}
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          )}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:text-destructive"
            disabled={selected.size === 0}
            onClick={removeSelected}
          >
            <Trash2 className="h-4 w-4" />
            Remove selected
          </Button>
        </div>
      </div>
    </Field>
  );
}
