import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * A deliberately small markdown for mod text: paragraphs, `# headings`, `- lists`, **bold**,
 * *italic*, `code` and [links](https://...). It builds React elements, so nothing a mod writes is
 * ever treated as HTML, and only https links become links.
 */
const INLINE = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\[[^\]]+\]\(https:\/\/[^)\s]+\))/g;

function inline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    const key = `${keyPrefix}-${i}`;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={key} className="rounded bg-muted px-1 py-0.5 text-[0.9em]">
          {part.slice(1, -1)}
        </code>
      );
    }
    const link = /^\[([^\]]+)\]\((https:\/\/[^)\s]+)\)$/.exec(part);
    if (link) {
      return (
        <a
          key={key}
          href={link[2]}
          target="_blank"
          rel="noreferrer noopener"
          className="text-primary underline-offset-2 hover:underline"
        >
          {link[1]}
        </a>
      );
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={key}>{part.slice(1, -1)}</em>;
    }
    return part;
  });
}

export function MarkdownLite({ text, className }: { text: string; className?: string }) {
  const blocks = text
    .replace(/\r\n/g, "\n")
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);

  return (
    <div className={cn("space-y-2 text-sm", className)}>
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        if (lines.every((line) => /^\s*[-*] /.test(line))) {
          return (
            <ul key={i} className="list-disc space-y-0.5 pl-5">
              {lines.map((line, j) => (
                <li key={j}>{inline(line.replace(/^\s*[-*] /, ""), `${i}-${j}`)}</li>
              ))}
            </ul>
          );
        }
        if (/^#{1,3} /.test(lines[0])) {
          return (
            <p key={i} className="font-semibold">
              {inline(lines[0].replace(/^#{1,3} /, ""), `${i}-h`)}
            </p>
          );
        }
        return <p key={i}>{inline(lines.join(" "), String(i))}</p>;
      })}
    </div>
  );
}
