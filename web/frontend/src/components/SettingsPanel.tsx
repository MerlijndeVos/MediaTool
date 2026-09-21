import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { fetchSettings, updateSettings, type AppSettings } from "@/api/client";
import { CheckField } from "@/components/fields";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface SettingsPanelProps {
  onFileLoggingChange?: (enabled: boolean) => void;
}

export function SettingsPanel({ onFileLoggingChange }: SettingsPanelProps) {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await fetchSettings();
      setSettings(data);
      onFileLoggingChange?.(data.file_logging);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [onFileLoggingChange]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleFileLoggingChange = async (enabled: boolean) => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const data = await updateSettings({ file_logging: enabled });
      setSettings(data);
      onFileLoggingChange?.(data.file_logging);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

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
          <CardTitle>Logging</CardTitle>
          <CardDescription>
            Operation logs are stored in the app data folder, not next to your media files.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <CheckField
            label="Save logs to disk"
            checked={settings.file_logging}
            onChange={handleFileLoggingChange}
            disabled={saving}
            hint="When off, logs appear in the panel only."
            tooltip="Log files are written under your local Toolbox data directory and can be cleared from the Logging page."
          />
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
