import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

function stripMarkdownInline(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, "$1").replace(/`(.+?)`/g, "$1");
}

export function ReleaseNotes({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  const items: ReactNode[] = [];

  for (const [index, line] of text.split("\n").entries()) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    if (trimmed.startsWith("### ")) {
      items.push(
        <h4 key={index} className="pt-3 text-sm font-semibold text-foreground first:pt-0">
          {stripMarkdownInline(trimmed.slice(4))}
        </h4>,
      );
      continue;
    }

    if (trimmed.startsWith("## ")) {
      items.push(
        <h3 key={index} className="pt-3 text-sm font-semibold text-foreground first:pt-0">
          {stripMarkdownInline(trimmed.slice(3))}
        </h3>,
      );
      continue;
    }

    if (trimmed.startsWith("# ")) {
      items.push(
        <h2 key={index} className="text-base font-semibold text-foreground">
          {stripMarkdownInline(trimmed.slice(2))}
        </h2>,
      );
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      items.push(
        <div key={index} className="flex gap-2 text-sm leading-relaxed text-muted-foreground">
          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
          <span>{stripMarkdownInline(trimmed.replace(/^[-*]\s+/, ""))}</span>
        </div>,
      );
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      items.push(
        <div key={index} className="flex gap-2 text-sm leading-relaxed text-muted-foreground">
          <span className="shrink-0 font-medium text-foreground">
            {trimmed.match(/^\d+/)?.[0]}.
          </span>
          <span>{stripMarkdownInline(trimmed.replace(/^\d+\.\s+/, ""))}</span>
        </div>,
      );
      continue;
    }

    items.push(
      <p key={index} className="text-sm leading-relaxed text-muted-foreground">
        {stripMarkdownInline(trimmed)}
      </p>,
    );
  }

  return <div className={cn("space-y-2", className)}>{items}</div>;
}
