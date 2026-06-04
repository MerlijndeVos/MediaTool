import { Upload } from "lucide-react";
import { cn } from "@/lib/utils";

interface DropZoneProps {
  onPaths: (paths: string[]) => void;
  hint?: string;
  className?: string;
  multi?: boolean;
}

/** Visual drop target; fills path field(s) from dropped file names (paste full paths when needed). */
export function DropZone({ onPaths, hint, className, multi = false }: DropZoneProps) {
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    if (!files.length) return;
    const paths = files.map((f) => {
      const fileWithPath = f as File & { path?: string };
      return fileWithPath.path ?? f.name;
    });
    onPaths(multi ? paths : [paths[0]]);
  };

  return (
    <div
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border bg-muted/40 px-6 py-10 text-center transition-colors hover:border-primary/50 hover:bg-muted/60",
        className,
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Upload className="h-6 w-6" />
      </div>
      <p className="text-sm font-medium">Drop files or folders here</p>
      <p className="max-w-sm text-xs text-muted-foreground">
        {hint ??
          "In the desktop app, full paths are filled automatically. In the browser, paste the full path in the field below."}
      </p>
    </div>
  );
}
