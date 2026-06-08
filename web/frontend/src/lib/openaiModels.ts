export interface OpenAiModelProfile {
  value: string;
  label: string;
  /** 1 (slowest) – 5 (fastest) */
  speed: number;
  /** 1 (most expensive) – 5 (cheapest) */
  costEfficiency: number;
  /** 1 (lowest) – 5 (best for subtitles) */
  quality: number;
  recommended?: boolean;
  summary: string;
  /** Rough wall-clock time for a typical ~90 min film (~800 cues). */
  typicalFilmTime: string;
}

export const OPENAI_MODEL_PROFILES: OpenAiModelProfile[] = [
  {
    value: "gpt-4o-mini",
    label: "GPT-4o mini",
    speed: 5,
    costEfficiency: 5,
    quality: 4,
    recommended: true,
    summary: "Best default for subtitles — fast, inexpensive, and reliably accurate.",
    typicalFilmTime: "~1–2 min per film",
  },
  {
    value: "gpt-4o",
    label: "GPT-4o",
    speed: 3,
    costEfficiency: 3,
    quality: 5,
    summary: "Higher translation quality and nuance; slower and costs more per file.",
    typicalFilmTime: "~2–4 min per film",
  },
  {
    value: "gpt-4.1-mini",
    label: "GPT-4.1 mini",
    speed: 5,
    costEfficiency: 4,
    quality: 4,
    summary: "Newer mini model — similar speed to 4o mini with slightly improved wording.",
    typicalFilmTime: "~1–2 min per film",
  },
  {
    value: "gpt-4.1",
    label: "GPT-4.1",
    speed: 3,
    costEfficiency: 2,
    quality: 5,
    summary: "Top-tier quality for difficult dialogue; best when accuracy matters most.",
    typicalFilmTime: "~2–5 min per film",
  },
  {
    value: "o4-mini",
    label: "o4-mini",
    speed: 2,
    costEfficiency: 3,
    quality: 4,
    summary: "Reasoning model — slower for batch subtitle work; rarely needed here.",
    typicalFilmTime: "~3–6 min per film",
  },
  {
    value: "o3-mini",
    label: "o3-mini",
    speed: 2,
    costEfficiency: 2,
    quality: 4,
    summary: "Heavier reasoning model — slowest option; use only for very hard source text.",
    typicalFilmTime: "~4–8 min per film",
  },
];

const PROFILE_BY_VALUE = new Map(OPENAI_MODEL_PROFILES.map((m) => [m.value, m]));

export function getOpenAiModelProfile(model: string): OpenAiModelProfile | undefined {
  return PROFILE_BY_VALUE.get(model);
}

export function metricLabel(kind: "speed" | "costEfficiency" | "quality", value: number): string {
  if (kind === "speed") {
    if (value >= 5) return "Very fast";
    if (value >= 4) return "Fast";
    if (value >= 3) return "Moderate";
    if (value >= 2) return "Slower";
    return "Slow";
  }
  if (kind === "costEfficiency") {
    if (value >= 5) return "Lowest cost";
    if (value >= 4) return "Low cost";
    if (value >= 3) return "Moderate";
    if (value >= 2) return "Higher cost";
    return "Premium cost";
  }
  if (value >= 5) return "Excellent";
  if (value >= 4) return "Very good";
  if (value >= 3) return "Good";
  return "Adequate";
}

/** Short summary for native select option text. */
export function modelDropdownLabel(profile: OpenAiModelProfile): string {
  const speed = metricLabel("speed", profile.speed).toLowerCase();
  const cost = metricLabel("costEfficiency", profile.costEfficiency).toLowerCase();
  const quality = metricLabel("quality", profile.quality).toLowerCase();
  const suffix = profile.recommended ? " · recommended" : "";
  return `${profile.label} — ${speed}, ${cost}, ${quality}${suffix}`;
}

export function openAiModelSelectOptions(currentModel?: string) {
  const options = OPENAI_MODEL_PROFILES.map((m) => ({
    value: m.value,
    label: modelDropdownLabel(m),
  }));
  if (currentModel && !PROFILE_BY_VALUE.has(currentModel)) {
    options.push({ value: currentModel, label: `${currentModel} (custom)` });
  }
  return options;
}
