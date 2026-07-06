import { useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import type {
  UsageAgentRank,
  UsagePluginRank,
  UsageSkillRank,
  UsageSummary,
  UsageTimeseriesPoint,
} from "@/types";
import { I } from "@/icons";
import { Btn } from "@/components/ui";

type RangeKey = "today" | "7d" | "30d" | "custom";

const emptyCustom = { start: "", end: "" };

export default function UsageAnalyticsPage() {
  const [range, setRange] = useState<RangeKey>("today");
  const [custom, setCustom] = useState(emptyCustom);
  const [data, setData] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [userIdFilter, setUserIdFilter] = useState("");
  const [userDisplayFilter, setUserDisplayFilter] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [queryKey, setQueryKey] = useState(0);

  useEffect(() => {
    if (range === "custom" && (!custom.start || !custom.end)) return;
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .adminUsageSummary({
        range,
        start: range === "custom" ? custom.start : undefined,
        end: range === "custom" ? custom.end : undefined,
        user: userIdFilter || undefined,
        department: departmentFilter || undefined,
      })
      .then((result) => {
        if (alive) setData(result);
      })
      .catch((err) => {
        if (alive) setError(formatError(err));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [range, custom.start, custom.end, queryKey]);

  const hasData = !!data && data.overview.call_count > 0;

  return (
    <div style={{ flex: 1, overflow: "auto", padding: 24 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 16,
          alignItems: "flex-end",
          marginBottom: 18,
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 650, color: "var(--ink)" }}>
            使用统计
          </h1>
          <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--ink-3)" }}>
            按时间段查看平台调用、智能体、技能、插件与 token 消耗
          </p>
        </div>
        <RangeControls range={range} custom={custom} onRange={setRange} onCustom={setCustom} />
      </div>

      <FilterBar
        userDisplay={userDisplayFilter}
        department={departmentFilter}
        onUserId={setUserIdFilter}
        onUserDisplay={setUserDisplayFilter}
        onDepartment={setDepartmentFilter}
        onQuery={() => setQueryKey((k) => k + 1)}
      />

      {loading ? (
        <StatePanel icon={<I.Loader size={18} />} text="正在加载使用统计..." />
      ) : error ? (
        <StatePanel icon={<I.CircleAlert size={18} />} text={error} />
      ) : !data || !hasData ? (
        <StatePanel icon={<I.Database size={18} />} text="当前时间范围暂无使用数据" />
      ) : (
        <div style={{ display: "grid", gap: 14 }}>
          <KpiGrid data={data} />
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0, 2fr) minmax(280px, 1fr)",
              gap: 14,
            }}
          >
            <ChartPanel title="调用与 token 趋势">
              <UsageBars points={data.timeseries} />
            </ChartPanel>
            <ChartPanel title="状态分布">
              <StatusBar data={data} />
            </ChartPanel>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 14 }}>
            <AgentRank rows={data.agents} />
            <SkillRank rows={data.skills} />
            <PluginRank rows={data.plugins} />
          </div>
        </div>
      )}
    </div>
  );
}

function RangeControls({
  range,
  custom,
  onRange,
  onCustom,
}: {
  range: RangeKey;
  custom: { start: string; end: string };
  onRange: (range: RangeKey) => void;
  onCustom: (value: { start: string; end: string }) => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        alignItems: "center",
        flexWrap: "wrap",
        justifyContent: "flex-end",
      }}
    >
      {(
        [
          ["today", "今天"],
          ["7d", "7 天"],
          ["30d", "30 天"],
          ["custom", "自定义"],
        ] as const
      ).map(([key, label]) => (
        <Btn key={key} size="sm" variant={range === key ? "primary" : "secondary"} onClick={() => onRange(key)}>
          {label}
        </Btn>
      ))}
      {range === "custom" && (
        <>
          <input
            type="date"
            value={custom.start}
            onChange={(e) => onCustom({ ...custom, start: e.target.value })}
            style={dateInputStyle}
          />
          <input
            type="date"
            value={custom.end}
            onChange={(e) => onCustom({ ...custom, end: e.target.value })}
            style={dateInputStyle}
          />
        </>
      )}
    </div>
  );
}

function FilterBar({
  userDisplay,
  department,
  onUserId,
  onUserDisplay,
  onDepartment,
  onQuery,
}: {
  userDisplay: string;
  department: string;
  onUserId: (v: string) => void;
  onUserDisplay: (v: string) => void;
  onDepartment: (v: string) => void;
  onQuery: () => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        alignItems: "center",
        flexWrap: "wrap",
        marginBottom: 18,
      }}
    >
      <UserSearchInput
        display={userDisplay}
        onDisplayChange={onUserDisplay}
        onUserIdChange={onUserId}
      />
      <FuzzyInput
        placeholder="部门（模糊搜索）"
        value={department}
        onChange={onDepartment}
        fetchSuggestions={(q) => api.adminUsageDepartments(q)}
      />
      <Btn size="sm" variant="primary" onClick={onQuery}>
        查询
      </Btn>
    </div>
  );
}

function UserSearchInput({
  display,
  onDisplayChange,
  onUserIdChange,
}: {
  display: string;
  onDisplayChange: (v: string) => void;
  onUserIdChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<
    { display_name: string; department: string | null; username: string }[]
  >([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function formatUser(item: { display_name: string; department: string | null }) {
    return item.department ? `${item.display_name}(${item.department})` : item.display_name;
  }

  function handleInput(v: string) {
    onDisplayChange(v);
    onUserIdChange("");
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!v.trim()) {
      setSuggestions([]);
      return;
    }
    timerRef.current = setTimeout(() => {
      api
        .adminUsageUsers(v.trim())
        .then((list) => {
          setSuggestions(list);
          setOpen(list.length > 0);
        })
        .catch(() => {
          setSuggestions([]);
          setOpen(false);
        });
    }, 200);
  }

  return (
    <div ref={wrapperRef} style={{ position: "relative" }}>
      <input
        type="text"
        placeholder="用户（模糊搜索）"
        value={display}
        onChange={(e) => handleInput(e.target.value)}
        onFocus={() => {
          if (suggestions.length > 0) setOpen(true);
        }}
        style={textInputStyle}
      />
      {open && suggestions.length > 0 && (
        <div style={dropdownStyle}>
          {suggestions.map((item) => (
            <div
              key={item.username}
              onClick={() => {
                onDisplayChange(formatUser(item));
                onUserIdChange(item.username);
                setOpen(false);
              }}
              style={{
                padding: "8px 12px",
                fontSize: 13,
                cursor: "pointer",
                color: "var(--ink)",
                borderBottom: "1px solid var(--line)",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLDivElement).style.background = "var(--bg-2)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLDivElement).style.background = "transparent";
              }}
            >
              {formatUser(item)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FuzzyInput({
  placeholder,
  value,
  onChange,
  fetchSuggestions,
}: {
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  fetchSuggestions: (q: string) => Promise<string[]>;
}) {
  const [open, setOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function handleInput(v: string) {
    onChange(v);
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!v.trim()) {
      setSuggestions([]);
      return;
    }
    timerRef.current = setTimeout(() => {
      fetchSuggestions(v.trim())
        .then((list) => {
          setSuggestions(list);
          setOpen(list.length > 0);
        })
        .catch(() => {
          setSuggestions([]);
          setOpen(false);
        });
    }, 200);
  }

  return (
    <div ref={wrapperRef} style={{ position: "relative" }}>
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => handleInput(e.target.value)}
        onFocus={() => {
          if (suggestions.length > 0) setOpen(true);
        }}
        style={textInputStyle}
      />
      {open && suggestions.length > 0 && (
        <div style={dropdownStyle}>
          {suggestions.map((item) => (
            <div
              key={item}
              onClick={() => {
                onChange(item);
                setOpen(false);
              }}
              style={{
                padding: "8px 12px",
                fontSize: 13,
                cursor: "pointer",
                color: "var(--ink)",
                borderBottom: "1px solid var(--line)",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLDivElement).style.background = "var(--bg-2)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLDivElement).style.background = "transparent";
              }}
            >
              {item}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function KpiGrid({ data }: { data: UsageSummary }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12 }}>
      <Kpi title="调用次数" value={formatNumber(data.overview.call_count)} />
      <Kpi title="活跃用户" value={formatNumber(data.overview.active_user_count)} />
      <Kpi
        title="总 Token"
        value={formatCompact(data.overview.total_tokens)}
        sub={`${formatCompact(data.overview.input_tokens)} 输入 / ${formatCompact(data.overview.output_tokens)} 输出`}
      />
      <Kpi
        title="错误 / 中断"
        value={`${data.overview.error_count} / ${data.overview.interrupted_count}`}
        sub={`平均耗时 ${formatDuration(data.overview.avg_duration_ms)}`}
      />
    </div>
  );
}

function Kpi({ title, value, sub }: { title: string; value: string; sub?: string }) {
  return (
    <div style={panelStyle}>
      <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{title}</div>
      <div style={{ marginTop: 8, fontSize: 24, fontWeight: 700, color: "var(--ink)" }}>{value}</div>
      {sub && <div style={{ marginTop: 6, fontSize: 12, color: "var(--ink-3)" }}>{sub}</div>}
    </div>
  );
}

function UsageBars({ points }: { points: UsageTimeseriesPoint[] }) {
  const max = Math.max(...points.map((p) => p.call_count), 1);
  return (
    <div style={{ height: 190, display: "flex", alignItems: "flex-end", gap: 6, paddingTop: 12 }}>
      {points.map((point) => (
        <div
          key={point.bucket}
          title={`${formatBucket(point.bucket)} · ${point.call_count} 次 · ${formatCompact(point.total_tokens)} token`}
          style={{
            flex: 1,
            minWidth: 8,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 6,
          }}
        >
          <div
            style={{
              width: "100%",
              height: `${Math.max(6, (point.call_count / max) * 150)}px`,
              background: "var(--accent)",
              borderRadius: "4px 4px 0 0",
              opacity: 0.78,
            }}
          />
          <span
            style={{
              fontSize: 10,
              color: "var(--ink-3)",
              writingMode: points.length > 12 ? "vertical-rl" : "horizontal-tb",
            }}
          >
            {formatBucket(point.bucket)}
          </span>
        </div>
      ))}
    </div>
  );
}

function StatusBar({ data }: { data: UsageSummary }) {
  const total = Math.max(data.overview.call_count, 1);
  const rows = ["success", "interrupted", "error"].map((status) => ({
    status,
    count: data.status_breakdown.find((item) => item.status === status)?.count ?? 0,
  }));
  return (
    <div>
      <div
        style={{
          display: "flex",
          height: 30,
          borderRadius: 999,
          overflow: "hidden",
          background: "var(--bg-3)",
          marginTop: 24,
        }}
      >
        {rows.map((row) => (
          <div key={row.status} style={{ width: `${(row.count / total) * 100}%`, background: statusColor(row.status) }} />
        ))}
      </div>
      <div style={{ display: "grid", gap: 10, marginTop: 20 }}>
        {rows.map((row) => (
          <div
            key={row.status}
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 13,
              color: "var(--ink-2)",
            }}
          >
            <span>{statusLabel(row.status)}</span>
            <strong>{row.count}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function AgentRank({ rows }: { rows: UsageAgentRank[] }) {
  return (
    <RankPanel title="智能体排行">
      {rows.map((row) => (
        <div key={`${row.agent_id}-${row.agent_name}`} style={rankRowStyle}>
          <div style={{ minWidth: 0 }}>
            <div style={rankTitleStyle}>{row.agent_name}</div>
            <div style={rankMetaStyle}>
              {row.active_user_count} 用户 · {formatCompact(row.total_tokens)} token · {row.error_count} 错误
            </div>
          </div>
          <strong>{row.call_count}</strong>
        </div>
      ))}
    </RankPanel>
  );
}

function SkillRank({ rows }: { rows: UsageSkillRank[] }) {
  return (
    <RankPanel title="Skill 排行">
      {rows.map((row) => (
        <SimpleRank key={row.resource_name} name={row.resource_name} count={row.trigger_count} />
      ))}
    </RankPanel>
  );
}

function PluginRank({ rows }: { rows: UsagePluginRank[] }) {
  return (
    <RankPanel title="Plugin 排行">
      {rows.map((row) => (
        <SimpleRank key={`${row.plugin_name}-${row.resource_name}`} name={row.resource_name} count={row.trigger_count} />
      ))}
    </RankPanel>
  );
}

function RankPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={panelStyle}>
      <h2 style={panelTitleStyle}>{title}</h2>
      <div style={{ display: "grid", gap: 10, marginTop: 12 }}>{children}</div>
    </div>
  );
}

function SimpleRank({ name, count }: { name: string; count: number }) {
  return (
    <div style={rankRowStyle}>
      <div style={rankTitleStyle}>{name}</div>
      <strong>{count}</strong>
    </div>
  );
}

function ChartPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={panelStyle}>
      <h2 style={panelTitleStyle}>{title}</h2>
      {children}
    </div>
  );
}

function StatePanel({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div
      style={{
        ...panelStyle,
        minHeight: 220,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        color: "var(--ink-3)",
      }}
    >
      {icon}
      <span>{text}</span>
    </div>
  );
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatCompact(value: number) {
  return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function formatDuration(value: number | null) {
  if (value == null) return "-";
  if (value < 1000) return `${Math.round(value)}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

function formatBucket(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit" }).format(date);
}

function statusLabel(status: string) {
  if (status === "success") return "成功";
  if (status === "interrupted") return "中断";
  if (status === "error") return "错误";
  return status;
}

function statusColor(status: string) {
  if (status === "success") return "var(--success)";
  if (status === "interrupted") return "#f59e0b";
  if (status === "error") return "var(--danger)";
  return "var(--ink-3)";
}

function formatError(error: unknown): string {
  return error instanceof Error ? error.message : "加载使用统计失败";
}

const panelStyle = {
  border: "1px solid var(--line)",
  borderRadius: 8,
  background: "var(--surface)",
  padding: 16,
  boxShadow: "var(--shadow-sm)",
} satisfies React.CSSProperties;

const panelTitleStyle = {
  margin: 0,
  fontSize: 15,
  fontWeight: 650,
  color: "var(--ink)",
} satisfies React.CSSProperties;

const rankRowStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: 12,
  alignItems: "center",
  minWidth: 0,
} satisfies React.CSSProperties;

const rankTitleStyle = {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  color: "var(--ink)",
  fontSize: 13,
} satisfies React.CSSProperties;

const rankMetaStyle = {
  marginTop: 3,
  color: "var(--ink-3)",
  fontSize: 12,
} satisfies React.CSSProperties;

const dateInputStyle = {
  height: 32,
  border: "1px solid var(--line)",
  borderRadius: 8,
  background: "var(--bg)",
  color: "var(--ink)",
  padding: "0 8px",
} satisfies React.CSSProperties;

const textInputStyle = {
  width: 180,
  height: 32,
  border: "1px solid var(--line)",
  borderRadius: 8,
  background: "var(--bg)",
  color: "var(--ink)",
  padding: "0 10px",
  fontSize: 13,
} satisfies React.CSSProperties;

const dropdownStyle = {
  position: "absolute" as const,
  top: "100%",
  left: 0,
  right: 0,
  marginTop: 4,
  maxHeight: 200,
  overflow: "auto" as const,
  background: "var(--surface)",
  border: "1px solid var(--line)",
  borderRadius: 8,
  zIndex: 10,
  boxShadow: "var(--shadow-sm)",
} satisfies React.CSSProperties;
