import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

function stripMarkdownInline(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, "$1").replace(/`(.+?)`/g, "$1");
}

function isTableSeparator(line: string): boolean {
  return /^\|[\s\-:|]+\|$/.test(line.trim());
}

function parseTableRow(line: string): string[] | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("|") || !trimmed.endsWith("|")) return null;
  if (isTableSeparator(trimmed)) return null;
  return trimmed
    .slice(1, -1)
    .split("|")
    .map((cell) => stripMarkdownInline(cell.trim()));
}

function ReleaseNotesTable({ rows }: { rows: string[][] }) {
  if (rows.length === 0) return null;

  const [header, ...body] = rows;

  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full min-w-[16rem] border-collapse text-sm">
        {header && (
          <thead>
            <tr className="border-b bg-muted/50">
              {header.map((cell, index) => (
                <th
                  key={index}
                  className="px-3 py-2 text-left font-semibold text-foreground"
                >
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {body.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-b last:border-b-0">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-3 py-2 text-muted-foreground">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ReleaseNotes({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  const items: ReactNode[] = [];
  const lines = text.split("\n");
  let index = 0;

  while (index < lines.length) {
    const trimmed = lines[index].trim();
    if (!trimmed) {
      index += 1;
      continue;
    }

    const tableRow = parseTableRow(trimmed);
    if (tableRow) {
      const tableRows: string[][] = [tableRow];
      index += 1;
      while (index < lines.length) {
        const next = lines[index].trim();
        if (!next || isTableSeparator(next)) {
          index += 1;
          if (isTableSeparator(next)) continue;
          break;
        }
        const parsed = parseTableRow(next);
        if (!parsed) break;
        tableRows.push(parsed);
        index += 1;
      }
      items.push(<ReleaseNotesTable key={`table-${index}`} rows={tableRows} />);
      continue;
    }

    if (trimmed.startsWith("### ")) {
      items.push(
        <h4 key={index} className="pt-3 text-sm font-semibold text-foreground first:pt-0">
          {stripMarkdownInline(trimmed.slice(4))}
        </h4>,
      );
      index += 1;
      continue;
    }

    if (trimmed.startsWith("## ")) {
      items.push(
        <h3 key={index} className="pt-3 text-sm font-semibold text-foreground first:pt-0">
          {stripMarkdownInline(trimmed.slice(3))}
        </h3>,
      );
      index += 1;
      continue;
    }

    if (trimmed.startsWith("# ")) {
      items.push(
        <h2 key={index} className="text-base font-semibold text-foreground">
          {stripMarkdownInline(trimmed.slice(2))}
        </h2>,
      );
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      items.push(
        <div key={index} className="flex gap-2 text-sm leading-relaxed text-muted-foreground">
          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
          <span>{stripMarkdownInline(trimmed.replace(/^[-*]\s+/, ""))}</span>
        </div>,
      );
      index += 1;
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
      index += 1;
      continue;
    }

    items.push(
      <p key={index} className="text-sm leading-relaxed text-muted-foreground">
        {stripMarkdownInline(trimmed)}
      </p>,
    );
    index += 1;
  }

  return <div className={cn("space-y-2", className)}>{items}</div>;
}
