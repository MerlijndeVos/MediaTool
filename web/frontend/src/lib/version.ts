export function normalizeVersion(value: string): string {
  return value.trim().replace(/^[vV]/, "");
}

export function isNewerVersionAvailable(
  current: string,
  latest: string | null | undefined,
  updateAvailable: boolean,
): boolean {
  if (!updateAvailable || !latest) return false;
  return normalizeVersion(current) !== normalizeVersion(latest);
}
