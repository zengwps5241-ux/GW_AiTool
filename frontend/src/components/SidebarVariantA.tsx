// 🧪 PROTOTYPE Variant A — "Elegant Sidebar"
// 所有页面在一个侧边栏中，用清晰的分组标签区分："作战台" / "文件" / "管理"
// 每个分组之间有分隔线，业务页面有微妙的视觉区分
import { useMemo } from "react";
import type { UserMe, ViewName } from "@/types";
import { I } from "@/icons";
import { Avatar } from "./ui";

interface NavItem {
  id: ViewName;
  label: string;
  icon: (p: { size?: number }) => JSX.Element;
  group: string;
}

function getNavItems(user: UserMe): NavItem[] {
  const items: NavItem[] = [
    // 作战台 — 核心业务页面
    { id: "chat", label: "对话", icon: I.MessageSquare, group: "作战台" },
    { id: "businessMap", label: "业务地图", icon: I.Map, group: "作战台" },
    { id: "marketingMap", label: "营销地图", icon: I.Target, group: "作战台" },
    { id: "visitRecords", label: "拜访记录", icon: I.ClipboardList, group: "作战台" },
    // 文件
    { id: "personalSpace", label: "个人空间", icon: I.Folder, group: "文件" },
    { id: "teamSpaces", label: "团队空间", icon: I.Folders, group: "文件" },
    // 管理
    { id: "agents", label: "智能体管理", icon: I.Brain, group: "管理" },
  ];
  if (user.role !== "user") {
    items.push({ id: "skills", label: "技能管理", icon: I.Puzzle, group: "管理" });
    items.push({ id: "usage", label: "使用统计", icon: I.LayoutDashboard, group: "管理" });
    items.push({ id: "feedback", label: "反馈管理", icon: I.MessageSquare, group: "管理" });
  }
  if (user.role === "super") {
    items.push({ id: "loginWhitelist", label: "用户白名单", icon: I.Users, group: "管理" });
  }
  // 设置（admin 可见，§2.1：组织架构 / 用户管理 等）
  if (user.role !== "user") {
    items.push({ id: "organization", label: "组织架构", icon: I.Building, group: "设置" });
    items.push({ id: "userApproval", label: "用户管理", icon: I.UserCheck, group: "设置" });
  }
  return items;
}

interface Props {
  current: ViewName;
  onNav: (v: ViewName) => void;
  collapsed: boolean;
  onToggle: () => void;
  user: UserMe;
  onLogout: () => void;
}

export default function SidebarVariantA({
  current,
  onNav,
  collapsed,
  onToggle,
  user,
  onLogout,
}: Props) {
  const groups = useMemo(() => {
    const out: Record<string, NavItem[]> = {};
    getNavItems(user).forEach((it) => {
      (out[it.group] ||= []).push(it);
    });
    return out;
  }, [user]);

  const groupOrder = ["作战台", "文件", "管理", "设置"];

  return (
    <aside
      style={{
        width: collapsed ? "var(--sidebar-w-collapsed)" : "var(--sidebar-w)",
        background: "var(--bg-2)",
        borderRight: "1px solid var(--line)",
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
        transition: "width 200ms ease",
        overflow: "hidden",
      }}
    >
      {/* 品牌 */}
      <div
        style={{
          height: "var(--topbar-h)",
          padding: "0 16px",
          display: "flex",
          alignItems: "center",
          gap: 10,
          borderBottom: "1px solid var(--line)",
        }}
      >
        <span style={{ color: "var(--accent)", flexShrink: 0, display: "flex" }}>
          <I.Logo size={22} />
        </span>
        {!collapsed && (
          <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.15 }}>
            <span
              style={{
                fontFamily: "var(--serif)",
                fontSize: 14,
                fontWeight: 600,
                color: "var(--ink)",
                letterSpacing: -0.01,
              }}
            >
              AI 顾问作战台
            </span>
            <span style={{ fontSize: 10, color: "var(--ink-3)" }}>智能体协作平台</span>
          </div>
        )}
      </div>

      {/* 导航分组 */}
      <div style={{ flex: 1, overflow: "auto", padding: "8px 8px" }}>
        {groupOrder.map((group) => {
          const items = groups[group];
          if (!items || items.length === 0) return null;
          return (
            <div key={group} style={{ marginBottom: group === "作战台" ? 16 : 8 }}>
              {/* 分组标签 + 分隔线 */}
              {!collapsed && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "8px 10px 6px",
                  }}
                >
                  {/* 作战台分组有一个小的 accent 色块 */}
                  {group === "作战台" && (
                    <span
                      style={{
                        width: 3,
                        height: 12,
                        borderRadius: 2,
                        background: "var(--accent)",
                        flexShrink: 0,
                      }}
                    />
                  )}
                  <span
                    style={{
                      fontSize: 10.5,
                      fontWeight: 700,
                      color: group === "作战台" ? "var(--accent)" : "var(--ink-3)",
                      textTransform: "uppercase",
                      letterSpacing: 0.8,
                    }}
                  >
                    {group}
                  </span>
                </div>
              )}
              {/* 分组间细分割线（折叠时也显示） */}
              {group !== "作战台" && (
                <div
                  style={{
                    height: 1,
                    background: "var(--line)",
                    margin: collapsed ? "8px 12px" : "4px 10px 8px",
                  }}
                />
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                {items.map((it) => {
                  const Ic = it.icon;
                  const active =
                    current === it.id ||
                    (it.id === "personalSpace" && current === "personalSpaceDetail") ||
                    (it.id === "teamSpaces" &&
                      (current === "teamSpaceChat" || current === "teamSpaceDetail"));
                  // 作战台项目用稍有不同的 active 样式
                  const isWarRoom = group === "作战台";
                  return (
                    <button
                      key={it.id}
                      onClick={() => onNav(it.id)}
                      title={collapsed ? it.label : undefined}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        padding: collapsed ? "9px 0" : "8px 10px",
                        justifyContent: collapsed ? "center" : "flex-start",
                        background: active
                          ? isWarRoom
                            ? "var(--accent-soft)"
                            : "var(--surface)"
                          : "transparent",
                        color: active ? "var(--ink)" : "var(--ink-2)",
                        border: "1px solid",
                        borderColor: active
                          ? isWarRoom
                            ? "var(--accent-soft)"
                            : "var(--line)"
                          : "transparent",
                        borderRadius: 8,
                        cursor: "pointer",
                        fontSize: 13.5,
                        fontWeight: active ? 600 : 400,
                        fontFamily: "inherit",
                        transition: "background 120ms, border-color 120ms, color 120ms",
                        boxShadow: active ? "var(--shadow-sm)" : "none",
                      }}
                      onMouseEnter={(e) => {
                        if (!active)
                          e.currentTarget.style.background = "var(--bg-3)";
                      }}
                      onMouseLeave={(e) => {
                        if (!active)
                          e.currentTarget.style.background = "transparent";
                      }}
                    >
                      <Ic size={16} />
                      {!collapsed && <span>{it.label}</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* 用户卡片 */}
      <div style={{ borderTop: "1px solid var(--line)", padding: 10 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: collapsed ? 0 : "6px 8px",
            justifyContent: collapsed ? "center" : "flex-start",
          }}
        >
          <Avatar name={user.display_name ?? user.username} size={28} />
          {!collapsed && (
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 500,
                  color: "var(--ink)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {user.display_name ?? user.username}
              </div>
              <div style={{ fontSize: 11, color: "var(--ink-3)" }}>已登录</div>
            </div>
          )}
          {!collapsed && (
            <button
              onClick={onLogout}
              className="focus-ring"
              title="退出登录"
              style={{
                background: "transparent",
                border: "none",
                color: "var(--ink-3)",
                cursor: "pointer",
                padding: 4,
                borderRadius: 6,
                display: "flex",
              }}
            >
              <I.LogOut size={16} />
            </button>
          )}
        </div>
        <button
          onClick={onToggle}
          className="focus-ring"
          title={collapsed ? "展开侧边栏" : "折叠侧边栏"}
          style={{
            width: "100%",
            marginTop: 6,
            background: "transparent",
            border: "none",
            color: "var(--ink-3)",
            cursor: "pointer",
            padding: 6,
            borderRadius: 6,
            display: "flex",
            justifyContent: "center",
          }}
        >
          {collapsed ? <I.ChevronRight size={16} /> : <I.PanelLeft size={16} />}
        </button>
      </div>
    </aside>
  );
}
