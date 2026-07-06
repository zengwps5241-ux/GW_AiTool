import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface FileNameTooltipProps {
  label: string;
  children: ReactNode;
  style?: CSSProperties;
}

interface TooltipPosition {
  left: number;
  top: number;
}

export default function FileNameTooltip({
  label,
  children,
  style,
}: FileNameTooltipProps) {
  const anchorRef = useRef<HTMLSpanElement | null>(null);
  const timerRef = useRef<number | null>(null);
  const [position, setPosition] = useState<TooltipPosition | null>(null);

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const hide = () => {
    clearTimer();
    setPosition(null);
  };

  const scheduleShow = () => {
    clearTimer();
    timerRef.current = window.setTimeout(() => {
      const rect = anchorRef.current?.getBoundingClientRect();
      if (!rect) return;
      setPosition({
        left: Math.max(8, Math.min(rect.left, window.innerWidth - 24)),
        top: Math.min(rect.bottom + 8, window.innerHeight - 48),
      });
    }, 500);
  };

  useEffect(() => {
    return clearTimer;
  }, []);

  useEffect(() => {
    if (!position) return;
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
    };
  }, [position]);

  return (
    <span
      ref={anchorRef}
      onMouseEnter={scheduleShow}
      onMouseLeave={hide}
      style={style}
    >
      {children}
      {position &&
        createPortal(
          <div
            style={{
              position: "fixed",
              left: position.left,
              top: position.top,
              zIndex: 3000,
              maxWidth: "min(420px, calc(100vw - 24px))",
              padding: "7px 10px",
              borderRadius: 8,
              border: "1px solid var(--line)",
              background: "var(--surface)",
              color: "var(--ink)",
              boxShadow: "0 12px 28px rgba(15, 23, 42, 0.18)",
              fontSize: 12.5,
              lineHeight: 1.45,
              wordBreak: "break-all",
              pointerEvents: "none",
            }}
          >
            {label}
          </div>,
          document.body,
        )}
    </span>
  );
}
