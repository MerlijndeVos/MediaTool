import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface AppearancePanelProps {
  dark: boolean;
  onDarkChange: (dark: boolean) => void;
}

export function AppearancePanel({ dark, onDarkChange }: AppearancePanelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
        <CardDescription>Choose light or dark theme for the Toolbox interface.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant={dark ? "outline" : "default"}
            size="default"
            onClick={() => onDarkChange(false)}
            className="gap-1.5"
          >
            <Sun className="h-4 w-4" />
            Light
          </Button>
          <Button
            type="button"
            variant={dark ? "default" : "outline"}
            size="default"
            onClick={() => onDarkChange(true)}
            className="gap-1.5"
          >
            <Moon className="h-4 w-4" />
            Dark
          </Button>
        </div>
        <p className={cn("mt-3 text-sm text-muted-foreground")}>
          {dark ? "Dark theme is active." : "Light theme is active."}
        </p>
      </CardContent>
    </Card>
  );
}
