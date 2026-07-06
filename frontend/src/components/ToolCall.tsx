// 工具调用块:展示 tool_use 与对应的 tool_result
import { useState, type ReactNode } from "react";
import { I } from "@/icons";
import { Spinner } from "@/components/ui";

type State = "calling" | "success" | "error";

interface Props {
  toolName: string;
  input: unknown;
  state: State;
  output?: unknown;
  errorText?: string;
}

// 安全地把任意值转成可读字符串
function stringify(v: unknown, max = 4000): string {
  if (v == null) return "";
  if (typeof v === "string") return v.length > max ? v.slice(0, max) + " …" : v;
  try {
    const s = JSON.stringify(v, null, 2);
    return s.length > max ? s.slice(0, max) + " …" : s;
  } catch {
    return String(v);
  }
}

export default function ToolCall({
  toolName,
  input,
  state,
  output,
  errorText,
}: Props) {
  const [open, setOpen] = useState(false);
  const tone = state === "calling" ? "info" : state === "error" ? "danger" : "success";
  const toneVar = tone === "info" ? "var(--info)" : tone === "danger" ? "var(--danger)" : "var(--success)";
  const toneSoft =
    tone === "info"
      ? "var(--info-soft)"
      : tone === "danger"
      ? "var(--danger-soft)"
      : "var(--success-soft)";

  // 标题图标
  let icon: ReactNode;
  if (state === "calling") icon = <Spinner size={12} />;
  else if (state === "error") icon = <I.CircleX size={13} />;
  else icon = <I.CircleCheck size={13} />;

  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        overflow: "hidden",
      }}
    >
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 12px",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          fontFamily: "inherit",
          textAlign: "left",
          color: "var(--ink)",
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 22,
            height: 22,
            borderRadius: 6,
            background: toneSoft,
            color: toneVar,
            flexShrink: 0,
          }}
        >
          {icon}
        </span>
        <span
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            gap: 8,
            minWidth: 0,
          }}
        >
          <code
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12.5,
              color: "var(--ink)",
              fontWeight: 500,
            }}
          >
            {toolName}
          </code>
          <span style={{ fontSize: 11, color: "var(--ink-3)" }}>
            {state === "calling" ? "调用中…" : state === "error" ? "失败" : "完成"}
          </span>
        </span>
        <I.ChevronDown
          size={14}
          style={{
            color: "var(--ink-3)",
            transform: open ? "rotate(180deg)" : undefined,
            transition: "transform 150ms",
          }}
        />
      </button>

      {open && (
        <div
          style={{
            padding: "0 12px 12px",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <Block label="输入参数">{stringify(input)}</Block>
          {output !== undefined && (
            <Block label="返回结果">{stringify(output)}</Block>
          )}
          {errorText && (
            <Block label="错误" tone="danger">
              {errorText}
            </Block>
          )}
        </div>
      )}
    </div>
  );
}

function Block({
  label,
  children,
  tone = "neutral",
}: {
  label: string;
  children: ReactNode;
  tone?: "neutral" | "danger";
}) {
  return (
    <div>
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: "var(--ink-3)",
          textTransform: "uppercase",
          letterSpacing: 0.5,
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <pre
        style={{
          margin: 0,
          padding: "8px 10px",
          background: tone === "danger" ? "var(--danger-soft)" : "var(--bg-2)",
          border: "1px solid var(--line)",
          borderRadius: 6,
          fontFamily: "var(--mono)",
          fontSize: 12,
          color: tone === "danger" ? "var(--danger)" : "var(--ink-2)",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          maxHeight: 280,
          overflow: "auto",
        }}
      >
        {children}
      </pre>
    </div>
  );
}
