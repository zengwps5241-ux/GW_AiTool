// 日志管理 tab（M6.6.5，决策 #71）
// 顶部筛选（操作人/操作类型/目标类型/时间范围）+ 下方表格（时间/操作人/操作/目标/摘要/IP）
// 点击行展开 detail：JSONB 变更快照 before→after 双列对比格式化显示
// 默认最近 7 天：未传时间范围时后端默认最近 7 天（决策 #69）；提供快捷预设按钮
import { useCallback, useEffect, useRef, useState } from "react";
import type { AuditLog, AuditLogFilter, AdminUser } from "@/types";
import { api } from "@/api/client";
import { I } from "@/icons";
import { Btn, Spinner } from "@/components/ui";

const PAGE_SIZE = 50;

/** 操作类型元数据（label + 配色）；覆盖后端 log_audit 的 action 取值 */
const ACTION_META: Record<string, { label: string; color: string; bg: string }> = {
  create: { label: "新增", color: "var(--success, #2e7d32)", bg: "var(--success-soft, #e8f5e9)" },
  update: { label: "修改", color: "var(--accent-2)", bg: "var(--accent-soft)" },
  delete: { label: "删除", color: "var(--danger)", bg: "var(--danger-soft)" },
  adopt: { label: "采纳", color: "var(--success, #2e7d32)", bg: "var(--success-soft, #e8f5e9)" },
  rollback: { label: "回滚", color: "var(--warn, #ed6c02)", bg: "var(--warn-soft, #fff3e0)" },
  approve: { label: "通过", color: "var(--success, #2e7d32)", bg: "var(--success-soft, #e8f5e9)" },
  reject: { label: "驳回", color: "var(--warn, #ed6c02)", bg: "var(--warn-soft, #fff3e0)" },
};

/** 目标类型中文映射（menu/role/user/organization/business_map/session + 审批草稿类） */
const TARGET_LABEL: Record<string, string> = {
  menu: "菜单",
  role: "角色",
  user: "用户",
  organization: "组织",
  business_map: "业务图谱",
  session: "会话",
  business_map_draft: "业务图谱草稿",
  stakeholder_card_draft: "干系人卡片草稿",
  visit_record_draft: "走访记录草稿",
};

/** 操作类型下拉可选项（与 ACTION_META 同源） */
const ACTION_OPTIONS = Object.keys(ACTION_META);
/** 目标类型下拉可选项（与 TARGET_LABEL 同源） */
const TARGET_OPTIONS = Object.keys(TARGET_LABEL);

/** 将 YYYY-MM-DD 转为带时分秒的 ISO 串（start → 00:00:00，end → 23:59:59） */
function dateToIso(date: string, endOfDay = false): string {
  if (!date) return "";
  return endOfDay ? `${date}T23:59:59` : `${date}T00:00:00`;
}

/** 本地日期串 YYYY-MM-DD（浏览器本地时区） */
function toStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
function todayStr(): string {
  return toStr(new Date());
}
function daysAgoStr(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return toStr(d);
}

/** 取对象的主标识（name/code/username/title 优先） */
function identOf(o: Record<string, unknown> | null): string | null {
  if (!o) return null;
  const v = o.name ?? o.code ?? o.username ?? o.title;
  return v == null ? null : String(v);
}

/** 从 detail 推导一句话摘要（变更字段列表 / 主标识） */
function summarize(log: AuditLog): string {
  const d = log.detail;
  if (!d) return "—";
  const before = (typeof d.before === "object" && d.before) ? (d.before as Record<string, unknown>) : null;
  const after = (typeof d.after === "object" && d.after) ? (d.after as Record<string, unknown>) : null;
  if (before && after) {
    const changed = Object.keys(after).filter(
      (k) => JSON.stringify(before[k]) !== JSON.stringify(after[k]),
    );
    if (changed.length) return `变更字段：${changed.join("、")}`;
    return "内容已更新";
  }
  if (after) {
    const id = identOf(after);
    return id ? `新建：${id}` : "已创建";
  }
  if (before) {
    const id = identOf(before);
    return id ? `删除：${id}` : "已删除";
  }
  return "—";
}

export default function AuditTab() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  // 筛选输入态（查询按钮触发后才应用到请求）
  const [fUserId, setFUserId] = useState("");
  const [fAction, setFAction] = useState("");
  const [fTarget, setFTarget] = useState("");
  const [fStart, setFStart] = useState("");
  const [fEnd, setFEnd] = useState("");

  // 已应用的筛选（供「加载更多」复用，避免读到未提交的输入态）
  const appliedRef = useRef<AuditLogFilter>({});

  /** 拉取一批日志；append=true 时追加到已有列表（加载更多） */
  const fetchLogs = useCallback(async (filter: AuditLogFilter, off: number, append: boolean) => {
    if (!append) setLoading(true);
    else setLoadingMore(true);
    setError("");
    try {
      const batch = await api.listAuditLogs({ ...filter, limit: PAGE_SIZE, offset: off });
      setLogs((prev) => (append ? [...prev, ...batch] : batch));
      // 返回数量等于页大小 → 可能还有更多
      setHasMore(batch.length === PAGE_SIZE);
      setOffset(off + batch.length);
    } catch {
      setError("获取审计日志失败");
      if (!append) setLogs([]);
      setHasMore(false);
    } finally {
      if (!append) setLoading(false);
      else setLoadingMore(false);
    }
  }, []);

  // 初次加载：操作人下拉 + 默认最近 7 天（空筛选 → 后端默认）
  useEffect(() => {
    api.listAdminUsers({}).then(setUsers).catch(() => {});
    void fetchLogs({}, 0, false);
  }, [fetchLogs]);

  /** 依据当前输入态 + 指定时间范围构造筛选并查询（预设按钮复用） */
  const runQuery = (start: string, end: string) => {
    const filter: AuditLogFilter = {};
    if (fUserId) filter.user_id = Number(fUserId);
    if (fAction) filter.action = fAction;
    if (fTarget) filter.target_type = fTarget;
    const s = dateToIso(start, false);
    const e = dateToIso(end, true);
    if (s) filter.start_date = s;
    if (e) filter.end_date = e;
    appliedRef.current = filter;
    void fetchLogs(filter, 0, false);
    setExpanded(new Set());
  };

  const handleQuery = () => runQuery(fStart, fEnd);

  const handleReset = () => {
    setFUserId("");
    setFAction("");
    setFTarget("");
    setFStart("");
    setFEnd("");
    appliedRef.current = {};
    void fetchLogs({}, 0, false);
    setExpanded(new Set());
  };

  // 快捷预设：直接以预设时间范围查询（同步回填输入态）
  const applyPreset = (kind: "7d" | "today" | "30d") => {
    let start = "";
    let end = "";
    if (kind === "today") {
      start = todayStr();
      end = todayStr();
    } else if (kind === "30d") {
      start = daysAgoStr(30);
      end = todayStr();
    } // 7d：start/end 留空 → 后端默认最近 7 天
    setFStart(start);
    setFEnd(end);
    runQuery(start, end);
  };

  const handleLoadMore = () => {
    void fetchLogs(appliedRef.current, offset, true);
  };

  const handleToggleExpand = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectStyle: React.CSSProperties = {
    padding: "6px 8px",
    fontSize: 12.5,
    borderRadius: 6,
    border: "1px solid var(--line)",
    background: "var(--surface)",
    color: "var(--ink-1)",
    outline: "none",
    height: 32,
  };

  const thStyle: React.CSSProperties = {
    textAlign: "left",
    padding: "8px 10px",
    fontSize: 11.5,
    fontWeight: 600,
    color: "var(--ink-3)",
    borderBottom: "1px solid var(--line)",
    whiteSpace: "nowrap",
  };
  const tdStyle: React.CSSProperties = {
    padding: "8px 10px",
    fontSize: 12.5,
    color: "var(--ink-1)",
    borderBottom: "1px solid var(--line)",
    verticalAlign: "middle",
  };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", gap: 10, minHeight: 0 }}>
      {/* 筛选栏 */}
      <div
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          flexWrap: "wrap",
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: 8,
          padding: 10,
        }}
      >
        <I.Filter size={14} style={{ color: "var(--ink-3)" }} />
        {/* 操作人：从用户列表选择（后端按 user_id 精确过滤） */}
        <select style={selectStyle} value={fUserId} onChange={(e) => setFUserId(e.target.value)}>
          <option value="">全部操作人</option>
          {users.map((u) => (
            <option key={u.id} value={String(u.id)}>
              {u.display_name || u.username}（{u.username}）
            </option>
          ))}
        </select>
        {/* 操作类型 */}
        <select style={selectStyle} value={fAction} onChange={(e) => setFAction(e.target.value)}>
          <option value="">全部操作</option>
          {ACTION_OPTIONS.map((a) => (
            <option key={a} value={a}>
              {ACTION_META[a].label}
            </option>
          ))}
        </select>
        {/* 目标类型 */}
        <select style={selectStyle} value={fTarget} onChange={(e) => setFTarget(e.target.value)}>
          <option value="">全部目标</option>
          {TARGET_OPTIONS.map((t) => (
            <option key={t} value={t}>
              {TARGET_LABEL[t]}
            </option>
          ))}
        </select>
        {/* 时间范围 */}
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--ink-3)" }}>
          <I.Calendar size={13} />
          <input
            type="date"
            style={selectStyle}
            value={fStart}
            onChange={(e) => setFStart(e.target.value)}
          />
          <span style={{ fontSize: 12, color: "var(--ink-3)" }}>至</span>
          <input
            type="date"
            style={selectStyle}
            value={fEnd}
            onChange={(e) => setFEnd(e.target.value)}
          />
        </span>
        {/* 快捷预设 */}
        <Btn variant="ghost" size="sm" onClick={() => applyPreset("7d")}>最近7天</Btn>
        <Btn variant="ghost" size="sm" onClick={() => applyPreset("today")}>今天</Btn>
        <Btn variant="ghost" size="sm" onClick={() => applyPreset("30d")}>最近30天</Btn>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <Btn variant="ghost" size="sm" onClick={handleReset}>重置</Btn>
          <Btn variant="primary" size="sm" onClick={handleQuery}>查询</Btn>
        </div>
      </div>

      {/* 统计 + 默认范围提示 */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--ink-3)" }}>
        <span>共 {logs.length} 条{hasMore ? "（可加载更多）" : ""}</span>
        {!fStart && !fEnd && <span>· 未选择时间范围，默认最近 7 天</span>}
      </div>

      {error && (
        <div
          style={{
            background: "var(--danger-soft)",
            color: "var(--danger)",
            padding: "8px 12px",
            borderRadius: 6,
            fontSize: 12.5,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <I.CircleAlert size={13} />
          {error}
        </div>
      )}

      {/* 表格 */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: "auto",
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: 8,
        }}
      >
        {loading ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
            <Spinner /> 加载中…
          </div>
        ) : logs.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
            暂无日志
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={thStyle}>时间</th>
                <th style={thStyle}>操作人</th>
                <th style={thStyle}>操作</th>
                <th style={thStyle}>目标</th>
                <th style={thStyle}>摘要</th>
                <th style={thStyle}>IP</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => {
                const isOpen = expanded.has(log.id);
                const am = ACTION_META[log.action] || { label: log.action, color: "var(--ink-3)", bg: "var(--bg-3)" };
                const tlabel = TARGET_LABEL[log.target_type] || log.target_type;
                return (
                  <LogRow
                    key={log.id}
                    log={log}
                    isOpen={isOpen}
                    am={am}
                    tlabel={tlabel}
                    tdStyle={tdStyle}
                    onToggle={() => handleToggleExpand(log.id)}
                  />
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* 加载更多 */}
      {hasMore && !loading && (
        <div style={{ display: "flex", justifyContent: "center" }}>
          <Btn variant="secondary" size="sm" disabled={loadingMore} onClick={handleLoadMore}>
            {loadingMore ? "加载中…" : "加载更多"}
          </Btn>
        </div>
      )}
    </div>
  );
}

/** 单行日志 + 展开后的 detail 快照（before→after 双列对比） */
function LogRow({
  log,
  isOpen,
  am,
  tlabel,
  tdStyle,
  onToggle,
}: {
  log: AuditLog;
  isOpen: boolean;
  am: { label: string; color: string; bg: string };
  tlabel: string;
  tdStyle: React.CSSProperties;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        style={{ cursor: "pointer" }}
        title={isOpen ? "点击收起" : "点击展开详情"}
      >
        <td style={{ ...tdStyle, whiteSpace: "nowrap", color: "var(--ink-2)" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--ink-3)" }}>
            {isOpen ? <I.ChevronDown size={12} /> : <I.ChevronRight size={12} />}
          </span>
          {log.created_at ? new Date(log.created_at).toLocaleString("zh-CN") : "—"}
        </td>
        <td style={tdStyle}>
          {log.username ? (
            <span style={{ fontWeight: 500 }}>{log.username}</span>
          ) : (
            <span style={{ color: "var(--ink-3)" }}>系统</span>
          )}
        </td>
        <td style={tdStyle}>
          <span
            style={{
              fontSize: 11,
              color: am.color,
              background: am.bg,
              padding: "2px 8px",
              borderRadius: 4,
              whiteSpace: "nowrap",
            }}
          >
            {am.label}
          </span>
        </td>
        <td style={{ ...tdStyle, whiteSpace: "nowrap" }}>
          {tlabel}
          {log.target_id ? (
            <span style={{ color: "var(--ink-3)" }}> #{log.target_id}</span>
          ) : null}
        </td>
        <td style={{ ...tdStyle, color: "var(--ink-2)" }}>{summarize(log)}</td>
        <td style={{ ...tdStyle, color: "var(--ink-3)", fontSize: 11.5 }}>{log.ip_address || "—"}</td>
      </tr>
      {isOpen && (
        <tr>
          <td colSpan={6} style={{ padding: "10px 14px", background: "var(--bg-3)", borderBottom: "1px solid var(--line)" }}>
            <DetailSnapshot log={log} />
          </td>
        </tr>
      )}
    </>
  );
}

/** 变更快照渲染：before→after 双列对比；仅 after 显示「新建内容」，仅 before 显示「删除内容」 */
function DetailSnapshot({ log }: { log: AuditLog }) {
  const d = log.detail;
  if (!d) {
    return <div style={{ fontSize: 12.5, color: "var(--ink-3)" }}>无快照数据</div>;
  }
  const before = (typeof d.before === "object" && d.before) ? (d.before as Record<string, unknown>) : null;
  const after = (typeof d.after === "object" && d.after) ? (d.after as Record<string, unknown>) : null;

  const labelStyle: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--ink-3)",
    marginBottom: 4,
  };
  const preStyle: React.CSSProperties = {
    margin: 0,
    padding: 10,
    fontSize: 12,
    fontFamily: "var(--mono, ui-monospace, monospace)",
    whiteSpace: "pre-wrap",
    wordBreak: "break-all",
    borderRadius: 6,
    border: "1px solid var(--line)",
    maxHeight: 320,
    overflow: "auto",
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        {before && (
          <div style={{ flex: "1 1 280px", minWidth: 240 }}>
            <div style={{ ...labelStyle, color: "var(--danger)" }}>变更前</div>
            <pre style={{ ...preStyle, background: "var(--danger-soft)" }}>
              {JSON.stringify(before, null, 2)}
            </pre>
          </div>
        )}
        {after && (
          <div style={{ flex: "1 1 280px", minWidth: 240 }}>
            <div style={{ ...labelStyle, color: "var(--success, #2e7d32)" }}>
              {before ? "变更后" : "新建内容"}
            </div>
            <pre style={{ ...preStyle, background: "var(--success-soft, #e8f5e9)" }}>
              {JSON.stringify(after, null, 2)}
            </pre>
          </div>
        )}
        {!before && !after && (
          <pre style={preStyle}>{JSON.stringify(d, null, 2)}</pre>
        )}
      </div>
      {/* 元信息：target_id / ip / 操作人 id */}
      <div style={{ marginTop: 8, fontSize: 11, color: "var(--ink-3)", display: "flex", gap: 16, flexWrap: "wrap" }}>
        {log.target_id && <span>目标 ID：{log.target_id}</span>}
        {log.ip_address && <span>IP：{log.ip_address}</span>}
        <span>操作人 ID：{log.user_id ?? "—"}</span>
      </div>
    </div>
  );
}
