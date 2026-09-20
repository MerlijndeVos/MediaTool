export type RuleType =
  | "replace"
  | "remove_words"
  | "remove_brackets"
  | "case"
  | "regex_replace";

export interface RenameRule {
  type: RuleType;
  find?: string;
  with?: string;
  words?: string[];
  brackets?: string[];
  mode?: string;
  pattern?: string;
}

export type PatternKey = "tv" | "movie" | "generic";

export interface RenameProfile {
  id?: string;
  name: string;
  rules: RenameRule[];
  patterns: Partial<Record<PatternKey, string>>;
  strip_release_junk: boolean;
  builtin?: boolean;
}

export type RenameMode = "media" | "generic";

export const RULE_LABELS: Record<RuleType, string> = {
  replace: "Replace text",
  remove_words: "Remove words",
  remove_brackets: "Remove bracketed text",
  case: "Letter case",
  regex_replace: "Regex replace (advanced)",
};

export const CASE_OPTIONS = [
  { value: "keep", label: "Keep as is" },
  { value: "title", label: "Title Case" },
  { value: "lower", label: "lower case" },
  { value: "upper", label: "UPPER CASE" },
  { value: "sentence", label: "Sentence case" },
];

export const BRACKET_KINDS = [
  { value: "[]", label: "[ ]" },
  { value: "()", label: "( )" },
  { value: "{}", label: "{ }" },
];

export const PATTERN_TOKENS: Record<PatternKey, string[]> = {
  tv: ["show", "season", "episode", "episode_end", "code", "title", "year"],
  movie: ["title", "year"],
  generic: ["name", "parent", "n"],
};

export const DEFAULT_PATTERNS: Record<PatternKey, string> = {
  tv: "{show} - {code} - {title}",
  movie: "{title} ({year})",
  generic: "{name}",
};

export const PATTERN_LABELS: Record<PatternKey, string> = {
  tv: "TV episode pattern",
  movie: "Movie pattern",
  generic: "Name pattern",
};

export function newRule(type: RuleType): RenameRule {
  switch (type) {
    case "replace":
      return { type, find: "", with: " " };
    case "remove_words":
      return { type, words: [] };
    case "remove_brackets":
      return { type, brackets: ["[]"] };
    case "case":
      return { type, mode: "title" };
    case "regex_replace":
      return { type, pattern: "", with: "" };
  }
}

export function emptyProfile(): RenameProfile {
  return {
    name: "My profile",
    rules: [{ type: "case", mode: "title" }],
    patterns: {},
    strip_release_junk: true,
  };
}

/** A copy without the identity, so saving creates a new profile. */
export function asNewProfile(profile: RenameProfile, name: string): RenameProfile {
  return { ...structuredClone(profile), id: undefined, builtin: false, name };
}

/** Split "before -> after" lines into examples. */
export function parseExamples(text: string): { before: string; after: string }[] {
  const examples: { before: string; after: string }[] = [];
  for (const line of text.split("\n")) {
    const match = line.match(/^(.*?)\s*(?:->|=>|→)\s*(.*)$/);
    if (!match) continue;
    const before = match[1].trim();
    const after = match[2].trim();
    if (before && after) examples.push({ before, after });
  }
  return examples;
}

export function profilesEqual(a: RenameProfile, b: RenameProfile): boolean {
  const strip = (p: RenameProfile) =>
    JSON.stringify({
      name: p.name,
      rules: p.rules,
      patterns: Object.fromEntries(Object.entries(p.patterns).filter(([, v]) => v)),
      strip_release_junk: p.strip_release_junk,
    });
  return strip(a) === strip(b);
}
