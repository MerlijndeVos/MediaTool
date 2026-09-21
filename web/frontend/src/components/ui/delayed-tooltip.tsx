import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { FocusEvent, PointerEvent, ReactNode, RefObject } from "react";
import { createPortal } from "react-dom";

const SHOW_DELAY_MS = 700;
const EDGE_GAP = 8;
const TRIGGER_GAP = 6;

interface TriggerProps {
  ref: RefObject<HTMLButtonElement | null>;
  "aria-describedby": string;
  onPointerEnter: (e: PointerEvent) => void;
  onPointerLeave: () => void;
  onPointerDown: () => void;
  onFocus: (e: FocusEvent) => void;
  onBlur: () => void;
}

interface DelayedTooltipProps {
  content: string;
  children: (trigger: TriggerProps) => ReactNode;
}

/**
 * Describes its trigger with a popover that appears after the pointer has rested on it for a moment
 * (so sweeping across several triggers shows nothing), or right away on keyboard focus. The text is
 * always available to screen readers through `aria-describedby`; the popover is only the visual copy.
 * It is drawn in a portal at a fixed position and kept inside the window, so no card can clip it.
 */
export function DelayedTooltip({ content, children }: DelayedTooltipProps) {
  const id = useId();
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const tipRef = useRef<HTMLDivElement | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  const cancel = useCallback(() => {
    window.clearTimeout(timer.current);
    setOpen(false);
    setPos(null);
  }, []);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  // Place the popover under the trigger (above it when there is no room), inside the window.
  useLayoutEffect(() => {
    const trigger = triggerRef.current;
    const tip = tipRef.current;
    if (!open || !trigger || !tip) return;
    const t = trigger.getBoundingClientRect();
    const { width, height } = tip.getBoundingClientRect();
    const left = Math.max(EDGE_GAP, Math.min(t.left, window.innerWidth - width - EDGE_GAP));
    const below = t.bottom + TRIGGER_GAP;
    const top =
      below + height + EDGE_GAP <= window.innerHeight
        ? below
        : Math.max(EDGE_GAP, t.top - TRIGGER_GAP - height);
    setPos({ top, left });
  }, [open]);

  // The popover is positioned in viewport coordinates, so drop it whenever the page moves under it.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") cancel();
    };
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", cancel, true);
    window.addEventListener("resize", cancel);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", cancel, true);
      window.removeEventListener("resize", cancel);
    };
  }, [open, cancel]);

  const trigger: TriggerProps = {
    ref: triggerRef,
    "aria-describedby": id,
    onPointerEnter: (e) => {
      // Touch has no resting hover; the tool's own page shows its description there.
      if (e.pointerType === "touch") return;
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setOpen(true), SHOW_DELAY_MS);
    },
    onPointerLeave: cancel,
    onPointerDown: cancel,
    onFocus: (e) => {
      // Only keyboard focus: a mouse click also focuses the button but must not pop a tooltip.
      if (e.target.matches(":focus-visible")) setOpen(true);
    },
    onBlur: cancel,
  };

  return (
    <>
      {children(trigger)}
      <span id={id} className="sr-only">
        {content}
      </span>
      {open &&
        createPortal(
          <div
            ref={tipRef}
            role="tooltip"
            style={{ top: pos?.top ?? 0, left: pos?.left ?? 0, visibility: pos ? "visible" : "hidden" }}
            className="pointer-events-none fixed z-50 w-max max-w-64 rounded-md border border-border bg-card px-2.5 py-1.5 text-left text-xs font-normal leading-snug text-foreground shadow-md"
          >
            {content}
          </div>,
          document.body,
        )}
    </>
  );
}
