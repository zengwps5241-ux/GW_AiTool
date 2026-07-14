// 系统设置页面（M6.6）：4-tab 统一管理（用户/角色/菜单/日志），决策 #66
// require admin 由路由守卫 + 后端 require_admin 双重保证。
// Tab 样式镜像 SkillsPage（底边 accent 下划线）。各 tab 实现在 ./system-settings/ 下。
import { useState } from "react";
import UsersTab from "./system-settings/UsersTab";
import RolesTab from "./system-settings/RolesTab";
import MenusTab from "./system-settings/MenusTab";
import AuditTab from "./system-settings/AuditTab";

type SettingsTab = "users" | "roles" | "menus" | "audit";

const TABS: { key: SettingsTab; label: string }[] = [
  { key: "users", label: "用户管理" },
  { key: "roles", label: "角色管理" },
  { key: "menus", label: "菜单管理" },
  { key: "audit", label: "日志管理" },
];

export default function SystemSettingsPage() {
  const [tab, setTab] = useState<SettingsTab>("users");

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        padding: "16px 20px",
        overflow: "auto",
      }}
    >
      {/* Tab 切换（底边 accent 下划线） */}
      <div
        style={{
          display: "flex",
          gap: 4,
          marginBottom: 16,
          borderBottom: "1px solid var(--line)",
        }}
      >
        {TABS.map((t) => {
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className="focus-ring"
              style={{
                padding: "8px 14px",
                fontSize: 13,
                fontWeight: active ? 500 : 400,
                color: active ? "var(--accent)" : "var(--ink-2)",
                borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
                background: "transparent",
                border: "none",
                borderBottomColor: active ? "var(--accent)" : "transparent",
                cursor: "pointer",
                transition: "color 120ms, border-color 120ms",
                marginBottom: -1,
              }}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      {/* Tab 内容 */}
      <div style={{ flex: 1, minHeight: 0 }}>
        {tab === "users" && <UsersTab />}
        {tab === "roles" && <RolesTab />}
        {tab === "menus" && <MenusTab />}
        {tab === "audit" && <AuditTab />}
      </div>
    </div>
  );
}
