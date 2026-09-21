import type { ShowIf } from "@/lib/types";

/** What a form field currently holds: text, a switch, or the ticked choices of a multi-choice. */
export type FormValue = string | boolean | string[];
export type FormValues = Record<string, FormValue>;

function isTruthy(value: FormValue | undefined): boolean {
  if (value === undefined) return false;
  if (typeof value === "boolean") return value;
  if (Array.isArray(value)) return value.length > 0;
  return value.trim() !== "";
}

function sameValue(value: FormValue | undefined, wanted: unknown): boolean {
  if (value === undefined || Array.isArray(value)) return false;
  // A number box holds text ("10"), a switch holds a boolean: compare how they read, not their type.
  return String(value) === String(wanted);
}

/** Should a field or section with this `show_if` be shown, given what the form holds now? */
export function isShown(condition: ShowIf | null | undefined, values: FormValues): boolean {
  if (!condition) return true;
  const value = values[condition.param];
  switch (condition.op) {
    case "truthy":
      return isTruthy(value);
    case "falsy":
      return !isTruthy(value);
    case "equals":
      return sameValue(value, condition.value);
    case "not_equals":
      return !sameValue(value, condition.value);
    case "in":
      return Array.isArray(condition.value) && condition.value.some((v) => sameValue(value, v));
    default:
      return true;
  }
}
