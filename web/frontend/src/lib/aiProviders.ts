import type { AiProviderId } from "@/api/client";
import { OPENAI_MODEL_PROFILES } from "@/lib/openaiModels";

export interface AiProviderInfo {
  id: AiProviderId;
  label: string;
  /** Shown as the API key placeholder. */
  keyPlaceholder: string;
  /** Environment variable that also supplies the key. */
  envVar?: string;
  /** Base URL is asked for (OpenAI-compatible only). */
  needsBaseUrl?: boolean;
  /** Local servers usually need no key. */
  keyOptional?: boolean;
  /** Suggestions only; any model id can be typed. */
  modelPresets: string[];
  modelPlaceholder?: string;
}

export const BASE_URL_PRESETS: { label: string; url: string }[] = [
  { label: "Ollama", url: "http://localhost:11434/v1" },
  { label: "LM Studio", url: "http://localhost:1234/v1" },
  { label: "OpenRouter", url: "https://openrouter.ai/api/v1" },
  { label: "Groq", url: "https://api.groq.com/openai/v1" },
  { label: "Together", url: "https://api.together.xyz/v1" },
  { label: "Mistral", url: "https://api.mistral.ai/v1" },
];

export const AI_PROVIDERS: AiProviderInfo[] = [
  {
    id: "openai",
    label: "OpenAI",
    keyPlaceholder: "sk-…",
    envVar: "OPENAI_API_KEY",
    modelPresets: OPENAI_MODEL_PROFILES.map((m) => m.value),
  },
  {
    id: "openai_compatible",
    label: "OpenAI-compatible",
    keyPlaceholder: "Only if the service asks for one",
    keyOptional: true,
    needsBaseUrl: true,
    modelPresets: [],
    modelPlaceholder: "e.g. llama3.1 (as named by your server)",
  },
  {
    id: "anthropic",
    label: "Anthropic (Claude)",
    keyPlaceholder: "sk-ant-…",
    envVar: "ANTHROPIC_API_KEY",
    modelPresets: ["claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-opus-5"],
  },
  {
    id: "gemini",
    label: "Google Gemini",
    keyPlaceholder: "AIza…",
    envVar: "GEMINI_API_KEY",
    modelPresets: ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-pro"],
  },
];

export function providerInfo(id: AiProviderId): AiProviderInfo {
  return AI_PROVIDERS.find((p) => p.id === id) ?? AI_PROVIDERS[0];
}

/** True when the base URL points at this computer, so nothing leaves the machine. */
export function isLocalUrl(url: string): boolean {
  const match = /^(?:[a-z]+:\/\/)?(\[[^\]]+\]|[^/:?#]+)/i.exec(url.trim());
  if (!match) return false;
  const host = match[1].toLowerCase();
  return host === "localhost" || host === "127.0.0.1" || host === "[::1]" || host.endsWith(".localhost");
}
