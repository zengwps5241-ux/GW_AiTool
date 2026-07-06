// 顶部栏:面包屑 + 主题切换
import { Fragment } from "react";
import type { ThemeMode } from "@/types";
import { I } from "@/icons";

export type BreadcrumbItem = string | { label: string; onClick?: () => void };

interface Props {
  breadcrumb: BreadcrumbItem[];
  theme: ThemeMode;
  onToggleTheme: () => void;
  onOpenFeedback: () => void;
}

export default function Topbar({ breadcrumb, theme, onToggleTheme, onOpenFeedback }: Props) {
  const labelOf = (item: BreadcrumbItem) => (typeof item === "string" ? item : item.label);

  return (
    <header
      style={{
        height: "var(--topbar-h)",
        borderBottom: "1px solid var(--line)",
        background: "var(--bg)",
        display: "flex",
        alignItems: "center",
        padding: "0 20px",
        flexShrink: 0,
        gap: 16,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 13,
          color: "var(--ink-3)",
          flex: 1,
          minWidth: 0,
        }}
      >
        {breadcrumb.map((b, i) => {
          const label = labelOf(b);
          const isLast = i === breadcrumb.length - 1;
          const onClick = typeof b === "string" ? undefined : b.onClick;
          return (
            <Fragment key={i}>
              {onClick ? (
                <button
                  type="button"
                  onClick={onClick}
                  style={{
                    all: "unset",
                    color: isLast ? "var(--ink)" : "var(--ink-3)",
                    fontWeight: isLast ? 500 : 400,
                    cursor: "pointer",
                  }}
                >
                  {label}
                </button>
              ) : (
                <span
                  style={{
                    color: isLast ? "var(--ink)" : "var(--ink-3)",
                    fontWeight: isLast ? 500 : 400,
                  }}
                >
                  {label}
                </span>
              )}
              {!isLast && (
                <I.ChevronRight size={12} style={{ color: "var(--ink-4)" }} />
              )}
            </Fragment>
          );
        })}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button
          onClick={onOpenFeedback}
          className="focus-ring"
          title="反馈问题"
          style={{
            background: "transparent",
            border: "1px solid var(--line)",
            color: "var(--ink-2)",
            cursor: "pointer",
            padding: 0,
            width: 32,
            height: 32,
            borderRadius: 8,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <I.MessageSquare size={15} />
        </button>
        <button
          onClick={onToggleTheme}
          className="focus-ring"
          title={theme === "dark" ? "切换浅色" : "切换深色"}
          style={{
            background: "transparent",
            border: "1px solid var(--line)",
            color: "var(--ink-2)",
            cursor: "pointer",
            padding: 0,
            width: 32,
            height: 32,
            borderRadius: 8,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {theme === "dark" ? <I.Sun size={15} /> : <I.Moon size={15} />}
        </button>
      </div>
    </header>
  );
}
