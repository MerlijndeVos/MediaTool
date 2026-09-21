import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { fetchMarket, prepareModInstall } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PermissionChips, PlacementChip, TrustNotice } from "@/components/ModBits";
import { Swatches } from "@/components/ThemePreview";
import type { MarketEntry, MarketResponse, ModInstallPreview } from "@/lib/types";

type TypeFilter = "all" | "tool" | "theme";

const TYPE_FILTERS: { id: TypeFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "tool", label: "Tools" },
  { id: "theme", label: "Themes" },
];

function matches(entry: MarketEntry, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const haystack = [entry.id, entry.name, entry.description, entry.author, entry.type, entry.group, ...entry.tags]
    .join(" ")
    .toLowerCase();
  return words.every((w) => haystack.includes(w));
}

interface ModMarketProps {
  installedIds: Set<string>;
  busy: boolean;
  onBusy: (busy: boolean) => void;
  onPrepared: (preview: ModInstallPreview) => void;
  onError: (message: string) => void;
}

/** Browse and search the public list of mods. Installing goes through the same review as any other install. */
export function ModMarket({ installedIds, busy, onBusy, onPrepared, onError }: ModMarketProps) {
  const [market, setMarket] = useState<MarketResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<TypeFilter>("all");

  const load = useCallback(async (refresh: boolean) => {
    setLoading(true);
    try {
      setMarket(await fetchMarket(refresh));
    } catch (e) {
      setMarket({
        url: "",
        mods: [],
        problems: [],
        error: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(false);
  }, [load]);

  const shown = useMemo(
    () =>
      (market?.mods ?? []).filter(
        (entry) => (kind === "all" || entry.type === kind) && matches(entry, query),
      ),
    [market, query, kind],
  );

  const install = async (entry: MarketEntry) => {
    onBusy(true);
    onError("");
    try {
      // The listing pins the commit; what the code really declares is checked against the listing.
      onPrepared(
        await prepareModInstall({
          location: entry.repo,
          ref: entry.commit,
          subdir: entry.path,
          expect: {
            id: entry.id,
            version: entry.version,
            type: entry.type,
            ...(entry.group ? { group: entry.group } : {}),
            ...(entry.permissions ? { permissions: entry.permissions } : {}),
          },
        }),
      );
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      onBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <TrustNotice>
        Listed is not reviewed. Anyone can list a mod, and the project does not check them. You
        see the real code, the exact commit and what the mod declares before anything is
        installed. Read it first.
      </TrustNotice>

      <div className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name, description, author or tag"
          aria-label="Search mods"
          className="min-w-0 flex-1"
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-10"
          disabled={loading}
          onClick={() => void load(true)}
        >
          <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
          Refresh
        </Button>
      </div>

      <div role="tablist" aria-label="Kind of mod" className="flex w-fit gap-1 rounded-lg bg-muted p-1">
        {TYPE_FILTERS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={kind === id}
            onClick={() => setKind(id)}
            className={
              "rounded-md px-3 py-1 text-sm font-medium transition-colors " +
              (kind === id ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground")
            }
          >
            {label}
          </button>
        ))}
      </div>

      {market?.error && (
        <p className="rounded-lg border border-danger/30 bg-danger/5 p-3 text-sm text-danger-text">
          {market.error}
        </p>
      )}
      {loading && !market && <p className="text-sm text-muted-foreground">Loading the list…</p>}
      {market && !market.error && (
        <p className="text-xs text-muted-foreground" role="status">
          {shown.length} of {market.mods.length} mods
          {market.problems.length > 0 && ` — ${market.problems.length} entries skipped (not valid)`}
        </p>
      )}

      <div className="grid gap-2.5 sm:grid-cols-2">
        {shown.map((entry) => (
          <div key={entry.id} className="flex flex-col gap-2 rounded-lg border border-border/60 p-3">
            <div>
              <p className="text-sm font-semibold leading-tight">
                {entry.name}
                <span className="ml-2 text-xs font-normal text-muted-foreground">v{entry.version}</span>
              </p>
              <p className="text-xs text-muted-foreground">
                {entry.author ? `by ${entry.author}` : "Author not stated"}
                {entry.license ? ` — ${entry.license}` : ""}
              </p>
            </div>
            {entry.description && <p className="text-xs">{entry.description}</p>}
            {entry.type === "theme" && entry.swatches.length > 0 && <Swatches colors={entry.swatches} />}
            <div className="flex flex-wrap items-center gap-2">
              {/* Where it appears is what the listing says; the real answer comes from the code in the install prompt. */}
              {entry.type === "theme" || entry.group ? (
                <PlacementChip type={entry.type} group={entry.group} />
              ) : (
                <span className="text-[11px] text-muted-foreground">Section not stated</span>
              )}
              {entry.type === "tool" && <PermissionChips permissions={entry.permissions} />}
            </div>
            {entry.tags.length > 0 && (
              <p className="flex flex-wrap gap-1.5">
                {entry.tags.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => setQuery(tag)}
                    className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
                  >
                    {tag}
                  </button>
                ))}
              </p>
            )}
            <div className="mt-auto flex items-center justify-between gap-2 pt-1">
              <span className="text-[11px] text-muted-foreground">Commit {entry.commit.slice(0, 10)}</span>
              {installedIds.has(entry.id) ? (
                <span className="text-xs font-medium text-muted-foreground">Installed</span>
              ) : (
                <Button type="button" size="sm" disabled={busy} onClick={() => void install(entry)}>
                  Review and install
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>
      {market && !market.error && shown.length === 0 && market.mods.length > 0 && (
        <p className="rounded-lg border border-dashed border-border/60 p-4 text-sm text-muted-foreground">
          No mods match that search.
        </p>
      )}
    </div>
  );
}
