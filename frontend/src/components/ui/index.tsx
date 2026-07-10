// 基础 UI 原语:按钮 / 输入 / 卡片 / 标签 / 头像 / 加载 / 提示框
// 设计语言对齐 ui-refer/ai-ops/ui.jsx,使用内联样式 + CSS 变量
import type {
  ButtonHTMLAttributes,
  CSSProperties,
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  TextareaHTMLAttributes,
} from "react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

type ToastVariant = "info" | "success" | "error";

interface ToastItem {
  id: number;
  message: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  showToast: (message: string, variant?: ToastVariant) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback((message: string, variant: ToastVariant = "info") => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message, variant }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, 3600);
  }, []);

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        style={{
          position: "fixed",
          right: 20,
          top: 20,
          zIndex: 120,
          display: "grid",
          gap: 8,
          width: "min(360px, calc(100vw - 40px))",
          pointerEvents: "none",
        }}
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            style={{
              pointerEvents: "auto",
              padding: "10px 12px",
              borderRadius: 10,
              background: "var(--bg)",
              border: `1px solid ${toastBorderColor(toast.variant)}`,
              boxShadow: "var(--shadow-lg)",
              color: toastTextColor(toast.variant),
              fontSize: 13,
              lineHeight: 1.5,
            }}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used inside ToastProvider");
  }
  return ctx;
}

function toastBorderColor(variant: ToastVariant): string {
  if (variant === "success") return "var(--success)";
  if (variant === "error") return "var(--danger)";
  return "var(--line)";
}

function toastTextColor(variant: ToastVariant): string {
  if (variant === "success") return "var(--success)";
  if (variant === "error") return "var(--danger)";
  return "var(--ink-2)";
}

// ============ ConfirmDialog ============
export function ConfirmDialog({
  open,
  title,
  message,
  confirmText = "确认",
  cancelText = "取消",
  onConfirm,
  onCancel,
  variant = "primary",
}: {
  open: boolean;
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
  onCancel: () => void;
  variant?: "primary" | "danger";
}) {
  if (!open) return null;
  return (
    <>
      {/* 遮罩 */}
      <div
        onClick={onCancel}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.32)",
          zIndex: 50,
          animation: "fade 160ms ease",
        }}
      />
      {/* 居中弹窗 */}
      <div
        role="dialog"
        aria-modal="true"
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 51,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            pointerEvents: "auto",
            width: "min(360px, 100%)",
            background: "var(--bg)",
            border: "1px solid var(--line)",
            borderRadius: 12,
            boxShadow: "var(--shadow-lg)",
            padding: "24px 20px 20px",
            display: "flex",
            flexDirection: "column",
            gap: 20,
            alignItems: "center",
            textAlign: "center",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "center" }}>
            {title && (
              <h3
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 16,
                  fontWeight: 500,
                  color: "var(--ink)",
                  margin: 0,
                }}
              >
                {title}
              </h3>
            )}
            <p
              style={{
                fontSize: 14,
                color: "var(--ink-2)",
                lineHeight: 1.55,
                margin: 0,
              }}
            >
              {message}
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, width: "100%" }}>
            <Btn variant="ghost" onClick={onCancel} block>
              {cancelText}
            </Btn>
            <Btn
              variant={variant}
              onClick={onConfirm}
              block
            >
              {confirmText}
            </Btn>
          </div>
        </div>
      </div>
    </>
  );
}

// ============ Button ============
type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "soft";
type BtnSize = "sm" | "md" | "lg";

interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: BtnVariant;
  size?: BtnSize;
  icon?: ReactNode;
  block?: boolean;
}

export function Btn({
  variant = "primary",
  size = "md",
  icon,
  block,
  children,
  style,
  className,
  ...rest
}: BtnProps) {
  const base: CSSProperties = {
    display: block ? "flex" : "inline-flex",
    width: block ? "100%" : undefined,
    alignItems: "center",
    gap: 6,
    justifyContent: "center",
    fontWeight: 500,
    fontSize: size === "sm" ? 13 : 14,
    lineHeight: 1,
    height: size === "sm" ? 28 : size === "lg" ? 40 : 34,
    padding: size === "sm" ? "0 10px" : size === "lg" ? "0 18px" : "0 14px",
    borderRadius: 8,
    border: "1px solid transparent",
    cursor: rest.disabled ? "not-allowed" : "pointer",
    opacity: rest.disabled ? 0.5 : 1,
    transition: "background-color 120ms, border-color 120ms, color 120ms",
    whiteSpace: "nowrap",
  };
  const variants: Record<BtnVariant, CSSProperties> = {
    primary: {
      background: "var(--accent)",
      color: "var(--on-accent)",
      borderColor: "var(--accent)",
    },
    secondary: {
      background: "var(--surface)",
      color: "var(--ink)",
      borderColor: "var(--line)",
    },
    ghost: {
      background: "transparent",
      color: "var(--ink-2)",
      borderColor: "transparent",
    },
    danger: {
      background: "var(--danger)",
      color: "var(--on-accent)",
      borderColor: "var(--danger)",
    },
    soft: {
      background: "var(--accent-soft)",
      color: "var(--accent-2)",
      borderColor: "transparent",
    },
  };
  return (
    <button
      {...rest}
      className={["focus-ring", className].filter(Boolean).join(" ")}
      style={{ ...base, ...variants[variant], ...style }}
    >
      {icon}
      {children}
    </button>
  );
}

// ============ Card ============
export function Card({
  children,
  style,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...rest}
      style={{
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: 12,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

// ============ Field ============
export function Field({
  label,
  hint,
  children,
}: {
  label?: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <label style={{ display: "block" }}>
      {label && (
        <div
          style={{
            fontSize: 13,
            fontWeight: 500,
            color: "var(--ink-2)",
            marginBottom: 6,
          }}
        >
          {label}
        </div>
      )}
      {children}
      {hint && (
        <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 6 }}>
          {hint}
        </div>
      )}
    </label>
  );
}

// ============ Input ============
interface InputBoxProps extends InputHTMLAttributes<HTMLInputElement> {
  icon?: ReactNode;
  rightIcon?: ReactNode;
  containerStyle?: CSSProperties;
}

export function Input({
  icon,
  rightIcon,
  containerStyle,
  style,
  ...rest
}: InputBoxProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: 8,
        padding: "0 12px",
        height: 38,
        transition: "border-color 120ms",
        ...containerStyle,
      }}
    >
      {icon && (
        <span style={{ color: "var(--ink-3)", display: "flex" }}>{icon}</span>
      )}
      <input
        {...rest}
        style={{
          flex: 1,
          border: "none",
          outline: "none",
          background: "transparent",
          fontSize: 14,
          color: "var(--ink)",
          height: "100%",
          ...style,
        }}
      />
      {rightIcon}
    </div>
  );
}

// ============ TextArea ============
interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  containerStyle?: CSSProperties;
}

export function TextArea({ style, containerStyle, ...rest }: TextAreaProps) {
  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: 8,
        padding: "10px 12px",
        transition: "border-color 120ms",
        ...containerStyle,
      }}
    >
      <textarea
        {...rest}
        style={{
          width: "100%",
          border: "none",
          outline: "none",
          resize: "vertical",
          background: "transparent",
          fontSize: 14,
          lineHeight: 1.55,
          color: "var(--ink)",
          fontFamily: "inherit",
          ...style,
        }}
      />
    </div>
  );
}

// ============ Tag ============
type Tone = "neutral" | "accent" | "success" | "warn" | "danger" | "info";

export function Tag({
  tone = "neutral",
  children,
  dot,
  style,
}: {
  tone?: Tone;
  children: ReactNode;
  dot?: boolean;
  style?: CSSProperties;
}) {
  const map: Record<Tone, { bg: string; fg: string }> = {
    neutral: { bg: "var(--bg-3)", fg: "var(--ink-2)" },
    accent: { bg: "var(--accent-soft)", fg: "var(--accent-2)" },
    success: { bg: "var(--success-soft)", fg: "var(--success)" },
    warn: { bg: "var(--warn-soft)", fg: "var(--warn)" },
    danger: { bg: "var(--danger-soft)", fg: "var(--danger)" },
    info: { bg: "var(--info-soft)", fg: "var(--info)" },
  };
  const t = map[tone];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        fontSize: 12,
        fontWeight: 500,
        padding: "2px 8px",
        borderRadius: 999,
        background: t.bg,
        color: t.fg,
        lineHeight: 1.4,
        ...style,
      }}
    >
      {dot && (
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: 999,
            background: t.fg,
          }}
        />
      )}
      {children}
    </span>
  );
}

// ============ Avatar ============
export function Avatar({
  name = "?",
  color,
  size = 28,
}: {
  name?: string;
  color?: string;
  size?: number;
}) {
  const palette = ["#6E8E68", "#6488A8", "#8C6F92", "#B07A2E", "#4A7593", "#5E8A55"];
  const c = color || palette[(name.charCodeAt(0) || 0) % palette.length];
  return (
    <span
      style={{
        width: size,
        height: size,
        borderRadius: 999,
        background: c,
        color: "var(--on-accent)",
        fontSize: size * 0.4,
        fontWeight: 600,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      {name[0]?.toUpperCase() || "?"}
    </span>
  );
}

// ============ Kbd ============
export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        minWidth: 18,
        height: 18,
        padding: "0 5px",
        fontSize: 11,
        fontFamily: "var(--mono)",
        color: "var(--ink-3)",
        background: "var(--bg-3)",
        border: "1px solid var(--line)",
        borderRadius: 4,
      }}
    >
      {children}
    </kbd>
  );
}

// ============ Spinner ============
export function Spinner({ size = 14 }: { size?: number }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: size,
        height: size,
        border: "1.6px solid var(--line-2)",
        borderTopColor: "var(--accent)",
        borderRadius: 999,
        animation: "spin 0.8s linear infinite",
      }}
    />
  );
}

// ============ TypingDots ============
export function TypingDots() {
  return (
    <span
      style={{
        display: "inline-flex",
        gap: 3,
        alignItems: "center",
        padding: "0 2px",
      }}
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 5,
            height: 5,
            borderRadius: 999,
            background: "var(--ink-3)",
            animation: `typing-dot 1.2s ${i * 0.15}s infinite`,
          }}
        />
      ))}
    </span>
  );
}

// ============ Checkbox ============
export function Checkbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: ReactNode;
}) {
  return (
    <label
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        fontSize: 13,
        color: "var(--ink-2)",
        cursor: "pointer",
      }}
    >
      <span
        onClick={() => onChange(!checked)}
        style={{
          width: 16,
          height: 16,
          borderRadius: 4,
          border: "1.5px solid " + (checked ? "var(--accent)" : "var(--line-2)"),
          background: checked ? "var(--accent)" : "transparent",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--on-accent)",
          flexShrink: 0,
        }}
      >
        {checked && (
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none">
            <path
              d="m5 12 5 5L20 7"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </span>
      {label}
    </label>
  );
}
