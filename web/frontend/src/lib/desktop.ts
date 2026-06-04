/** Native file dialogs when running inside the pywebview desktop shell. */

declare global {
  interface Window {
    pywebview?: {
      api?: {
        pick_folder(): Promise<string | null>;
        pick_files(multiple?: boolean): Promise<string[]>;
        pick_save_file(suggested_filename?: string): Promise<string | null>;
      };
    };
  }
}

export function isDesktopApp(): boolean {
  return typeof window.pywebview?.api?.pick_folder === "function";
}

export async function pickFolder(): Promise<string | null> {
  const api = window.pywebview?.api;
  if (!api?.pick_folder) return null;
  return api.pick_folder();
}

export async function pickFiles(multiple = false): Promise<string[]> {
  const api = window.pywebview?.api;
  if (!api?.pick_files) return [];
  return api.pick_files(multiple);
}

export async function pickSaveFile(suggestedFilename = ""): Promise<string | null> {
  const api = window.pywebview?.api;
  if (!api?.pick_save_file) return null;
  return api.pick_save_file(suggestedFilename);
}
