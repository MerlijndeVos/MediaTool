import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { fetchSettings, updateSettings, type AppSettings } from "@/api/client";
import { SelectField } from "@/components/fields";
import { ModelPerformanceIndicator } from "@/components/ModelPerformanceIndicator";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getOpenAiModelProfile, openAiModelSelectOptions } from "@/lib/openaiModels";

export function OpenAiSettingsPanel() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await fetchSettings();
      setSettings(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleModelChange = async (model: string) => {
    if (!settings) return;
    setSettings((prev) => (prev ? { ...prev, openai_model: model } : prev));
    setSaving(true);
    setError(null);
    try {
      const data = await updateSettings({ openai_model: model });
      setSettings(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const selectedProfile = useMemo(
    () => (settings ? getOpenAiModelProfile(settings.openai_model) : undefined),
    [settings],
  );

  const modelOptions = useMemo(
    () => (settings ? openAiModelSelectOptions(settings.openai_model) : []),
    [settings],
  );

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading settings…
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
        {error ?? "Could not load settings."}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>OpenAI translation</CardTitle>
          <CardDescription>
            Used by subtitle translation. Stored locally in your app data folder.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="openai-api-key">
              API key
            </label>
            <Input
              id="openai-api-key"
              type="password"
              autoComplete="off"
              placeholder={settings.openai_api_key_set ? "•••••••• (saved — enter to replace)" : "sk-…"}
              onBlur={async (e) => {
                const value = e.target.value.trim();
                if (!value) return;
                setSaving(true);
                setError(null);
                try {
                  const data = await updateSettings({ openai_api_key: value });
                  setSettings(data);
                  e.target.value = "";
                } catch (err) {
                  setError(err instanceof Error ? err.message : String(err));
                } finally {
                  setSaving(false);
                }
              }}
              disabled={saving}
            />
            <p className="text-xs text-muted-foreground">
              {settings.openai_api_key_set
                ? "A key is saved. Paste a new one to replace it."
                : "Required for subtitle translation. You can also set OPENAI_API_KEY."}
            </p>
          </div>

          <SelectField
            label="Model"
            value={settings.openai_model}
            onChange={(model) => void handleModelChange(model)}
            options={modelOptions}
            tooltip="Chat model used for subtitle translation."
            hint="Compare speed, cost, and quality below. Ratings are relative to the models in this list."
            disabled={saving}
          />

          {selectedProfile ? (
            <ModelPerformanceIndicator profile={selectedProfile} />
          ) : (
            <p className="rounded-lg border border-border/60 bg-muted/20 px-4 py-3 text-xs text-muted-foreground">
              Custom model <span className="font-mono">{settings.openai_model}</span> — no
              performance estimate available.
            </p>
          )}
        </CardContent>
      </Card>

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}
    </div>
  );
}
