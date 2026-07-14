// 🧪 PROTOTYPE Variant A — "Elegant Sidebar"
// 所有页面在一个侧边栏中，用清晰的分组标签区分："作战台" / "文件" / "管理" / "设置"
// 每个分组之间有分隔线，业务页面有微妙的视觉区分
//
// M6.5 数据驱动渲染（决策 #67）：菜单树由 App 登录后调 GET /api/menus 一次性加载并传入。
// 顶层节点 = 分组（view_name=null、children 非空），叶子节点 = 可点击菜单项（view_name 非空）。
// 不再硬编码 getNavItems，角色可见性完全由后端 role_menus 决定。
import { useMemo } from "react";
import type { MenuNode, UserMe, ViewName } from "@/types";
import { I } from "@/icons";
import { Avatar } from "./ui";

/** 图标名 → I 组件映射（后端菜单 icon 字段存 Lucide 图标名，决策 #59 种子迁移自原硬编码）。
 * 自定义菜单若用了未映射的图标名，回退到 CircleDot。 */
const ICON_MAP: Record<string, (p: { size?: number }) => JSX.Element> = {
  MessageSquare: I.MessageSquare,
  Map: I.Map,
  Target: I.Target,
  ClipboardList: I.ClipboardList,
  Folder: I.Folder,
  Folders: I.Folders,
  Brain: I.Brain,
  Puzzle: I.Puzzle,
  LayoutDashboard: I.LayoutDashboard,
  Users: I.Users,
  Settings: I.Settings,
};

/** 未知图标兜底（自定义菜单用了未映射的图标名时） */
const FallbackIcon = I.CircleDot;

/** 叶子菜单项（可点击） */
interface NavLeaf {
  view: ViewName;
  label: string;
  Icon: (p: { size?: number }) => JSX.Element;
}

/** 分组（顶层菜单节点） */
interface NavGroup {
  code: string;
  label: string;
  leaves: NavLeaf[];
}

/** 由菜单树构建可渲染的分组列表（顶层节点=分组，children=叶子）。
 * 后端已按 sort_order 返回，此处保持后端顺序不再排序。 */
function buildGroups(menuTree: MenuNode[]): NavGroup[] {
  return menuTree
    .map((node) => {
      const leaves: NavLeaf[] = (node.children ?? [])
        .filter((leaf) => leaf.view_name) // 仅渲染有 view_name 的叶子
        .map((leaf) => ({
          view: leaf.view_name as ViewName,
          label: leaf.name,
          Icon: ICON_MAP[leaf.icon ?? ""] ?? FallbackIcon,
        }));
      return { code: node.code, label: node.name, leaves };
    })
    .filter((g) => g.leaves.length > 0); // 空分组不显示
}

interface Props {
  current: ViewName;
  onNav: (v: ViewName) => void;
  collapsed: boolean;
  onToggle: () => void;
  user: UserMe;
  /** 当前用户可见菜单树（M6.5 数据驱动，App 登录后加载传入） */
  menuTree: MenuNode[];
  onLogout: () => void;
}

export default function SidebarVariantA({
  current,
  onNav,
  collapsed,
  onToggle,
  user,
  menuTree,
  onLogout,
}: Props) {
  const groups = useMemo(() => buildGroups(menuTree), [menuTree]);

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

      {/* 导航分组（数据驱动，按后端 sort_order 顺序渲染） */}
      <div style={{ flex: 1, overflow: "auto", padding: "8px 8px" }}>
        {groups.map((group) => {
          // 作战台分组用稍有不同的视觉（accent 色块 + accent 标签色）
          const isWarRoom = group.code === "group_zhanzuo";
          return (
            <div key={group.code} style={{ marginBottom: isWarRoom ? 16 : 8 }}>
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
                  {isWarRoom && (
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
                      color: isWarRoom ? "var(--accent)" : "var(--ink-3)",
                      textTransform: "uppercase",
                      letterSpacing: 0.8,
                    }}
                  >
                    {group.label}
                  </span>
                </div>
              )}
              {/* 分组间细分割线（折叠时也显示） */}
              {!isWarRoom && (
                <div
                  style={{
                    height: 1,
                    background: "var(--line)",
                    margin: collapsed ? "8px 12px" : "4px 10px 8px",
                  }}
                />
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                {group.leaves.map((it) => {
                  const Ic = it.Icon;
                  const active =
                    current === it.view ||
                    (it.view === "personalSpace" && current === "personalSpaceDetail") ||
                    (it.view === "teamSpaces" &&
                      (current === "teamSpaceChat" || current === "teamSpaceDetail"));
                  return (
                    <button
                      key={`${group.code}-${it.view}`}
                      onClick={() => onNav(it.view)}
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
