import type { OpenAiModelProfile } from "@/lib/openaiModels";
import { metricLabel } from "@/lib/openaiModels";
import { cn } from "@/lib/utils";

function MetricBar({
  label,
  kind,
  value,
  max = 5,
}: {
  label: string;
  kind: "speed" | "costEfficiency" | "quality";
  value: number;
  max?: number;
}) {
  const clamped = Math.min(max, Math.max(1, value));
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium text-foreground">{metricLabel(kind, clamped)}</span>
      </div>
      <div className="flex gap-1" role="img" aria-label={`${label}: ${metricLabel(kind, clamped)}`}>
        {Array.from({ length: max }, (_, index) => (
          <div
            key={index}
            className={cn(
              "h-1.5 flex-1 rounded-full transition-colors",
              index < clamped ? "bg-primary" : "bg-muted",
            )}
          />
        ))}
      </div>
    </div>
  );
}

export function ModelPerformanceIndicator({ profile }: { profile: OpenAiModelProfile }) {
  return (
    <div className="space-y-3 rounded-lg border border-border/60 bg-muted/20 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{profile.label}</p>
          <p className="mt-1 text-xs text-muted-foreground">{profile.summary}</p>
        </div>
        {profile.recommended && (
          <span className="shrink-0 rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
            Recommended
          </span>
        )}
      </div>

      <div className="space-y-3">
        <MetricBar label="Speed" kind="speed" value={profile.speed} />
        <MetricBar label="Cost" kind="costEfficiency" value={profile.costEfficiency} />
        <MetricBar label="Translation quality" kind="quality" value={profile.quality} />
      </div>

      <p className="text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Typical batch time:</span>{" "}
        {profile.typicalFilmTime} · Estimates are relative for a ~90 minute film; actual time
        depends on cue count and API load.
      </p>
    </div>
  );
}
