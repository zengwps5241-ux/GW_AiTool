// 应用根组件:鉴权门 + 主题切换 + 顶层视图路由
import { useEffect, useState, useCallback } from "react";
import { api } from "@/api/client";
import type { TeamSpace, ThemeMode, UserMe, ViewName } from "@/types";
import LoginPage from "@/pages/LoginPage";
import ChatWorkspace from "@/pages/ChatWorkspace";
import WorkspacePage from "@/pages/WorkspacePage";
import TeamSpacesPage from "@/pages/TeamSpacesPage";
import TeamSpaceDetailPage from "@/pages/TeamSpaceDetailPage";
import AgentsPage from "@/pages/AgentsPage";
import SkillsPage from "@/pages/SkillsPage";
import FeedbackAdminPage from "@/pages/FeedbackAdminPage";
import UsageAnalyticsPage from "@/pages/UsageAnalyticsPage";
import LoginWhitelistPage from "@/pages/LoginWhitelistPage";
import Sidebar from "@/components/Sidebar";
import Topbar, { type BreadcrumbItem } from "@/components/Topbar";
import FeedbackDialog from "@/components/FeedbackDialog";

type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "logged_in"; me: UserMe };

const THEME_KEY = "goktech.theme";
const SIDEBAR_KEY = "goktech.sidebar_collapsed";

export default function App() {
  const loginError = new URLSearchParams(window.location.search).get("error");
  const [auth, setAuth] = useState<AuthState>({ status: "loading" });
  const [loginMode, setLoginMode] = useState<"qrcode" | "sso" | null>(null);
  const [view, setView] = useState<ViewName>("chat");
  const [selectedTeamSpaceId, setSelectedTeamSpaceId] = useState<number | null>(null);
  const [selectedTeamSpaceName, setSelectedTeamSpaceName] = useState<string | null>(null);
  const [chatBreadcrumb, setChatBreadcrumb] = useState<BreadcrumbItem[]>(["对话工作台"]);
  const [initialTeamSpaceFilterVersion, setInitialTeamSpaceFilterVersion] = useState(0);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [theme, setTheme] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem(THEME_KEY);
    return saved === "dark" ? "dark" : "light";
  });
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    return localStorage.getItem(SIDEBAR_KEY) === "1";
  });

  const loadLoginMode = useCallback(async () => {
    try {
      const config = await api.wechatWorkConfig();
      setLoginMode(config.mode === "sso" ? "sso" : "qrcode");
    } catch {
      setLoginMode("qrcode");
    }
  }, []);

  // 同步主题到 <html data-theme="...">,并写入 localStorage
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  // 初始化:拉取当前用户及登录模式配置
  useEffect(() => {
    let alive = true;
    api
      .me()
      .then((me) => {
        if (alive) setAuth({ status: "logged_in", me });
      })
      .catch(() => {
        if (!alive) return;
        // 获取登录模式配置,失败时默认使用 qrcode。
        void loadLoginMode();
        if (alive) setAuth({ status: "anonymous" });
      });
    return () => {
      alive = false;
    };
  }, [loadLoginMode]);

  const handleLogout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // 即使后端失败也按已登出处理
    }
    await loadLoginMode();
    setAuth({ status: "anonymous" });
  }, [loadLoginMode]);

  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }, []);

  const openTeamChat = useCallback((space: TeamSpace) => {
    setSelectedTeamSpaceId(space.id);
    setSelectedTeamSpaceName(space.name);
    setInitialTeamSpaceFilterVersion((version) => version + 1);
    setView("chat");
  }, []);

  const openSelectedTeamChat = useCallback(() => {
    if (!selectedTeamSpaceId) return;
    setInitialTeamSpaceFilterVersion((version) => version + 1);
    setView("chat");
  }, [selectedTeamSpaceId]);

  const openTeamDetail = useCallback((space: TeamSpace) => {
    setSelectedTeamSpaceId(space.id);
    setSelectedTeamSpaceName(space.name);
    setView("teamSpaceDetail");
  }, []);

  const openTeamDetailById = useCallback((space: { id: number; name: string }) => {
    setSelectedTeamSpaceId(space.id);
    setSelectedTeamSpaceName(space.name);
    setView("teamSpaceDetail");
  }, []);

  const openTeamSpaces = useCallback(() => {
    setView("teamSpaces");
  }, []);

  const openSelectedTeamDetail = useCallback(() => {
    if (selectedTeamSpaceId) {
      setView("teamSpaceDetail");
    }
  }, [selectedTeamSpaceId]);

  const handleNav = useCallback((nextView: ViewName) => {
    if (nextView === "chat") {
      setSelectedTeamSpaceId(null);
      setSelectedTeamSpaceName(null);
      setChatBreadcrumb(["对话工作台"]);
    }
    setView(nextView);
  }, []);

  if (auth.status === "loading") {
    return (
      <div
        style={{
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--ink-3)",
          fontSize: 13,
        }}
      >
        加载中…
      </div>
    );
  }

  if (auth.status === "anonymous") {
    if (loginMode === "sso" && !loginError) {
      window.location.href = "/api/auth/wechat-work/authorize";
      return (
        <div
          style={{
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--ink-3)",
            fontSize: 13,
          }}
        >
          正在跳转至企业微信登录…
        </div>
      );
    }
    if (loginMode === null) {
      return (
        <div
          style={{
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--ink-3)",
            fontSize: 13,
          }}
        >
          加载中…
        </div>
      );
    }
    return <LoginPage mode={loginMode} />;
  }

  // 已登录:主壳布局
  const breadcrumb: BreadcrumbItem[] =
    view === "personalSpace"
      ? ["个人空间", "文件管理"]
      : view === "personalSpaceDetail" || view === "workspace"
      ? ["个人空间", "文件管理"]
      : view === "teamSpaces"
      ? ["团队空间", "空间列表"]
    : view === "teamSpaceChat"
      ? [
          { label: "团队空间", onClick: openTeamSpaces },
          { label: selectedTeamSpaceName || "团队空间", onClick: openSelectedTeamDetail },
          "会话",
        ]
      : view === "teamSpaceDetail"
      ? [{ label: "团队空间", onClick: openTeamSpaces }, selectedTeamSpaceName || "空间详情"]
      : view === "agents"
      ? ["管理", "智能体"]
      : view === "feedback"
      ? ["管理", "反馈管理"]
      : view === "skills"
      ? ["管理", "技能管理"]
      : view === "loginWhitelist"
      ? ["管理", "用户白名单"]
      : view === "usage"
      ? ["管理", "使用统计"]
    : view === "chat"
      ? chatBreadcrumb
      : ["对话工作台"];

  return (
    <div style={{ height: "100%", display: "flex", background: "var(--bg)" }}>
      <Sidebar
        current={view}
        onNav={handleNav}
        collapsed={collapsed}
        onToggle={() => setCollapsed((c) => !c)}
        user={auth.me}
        onLogout={handleLogout}
      />
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minWidth: 0,
        }}
      >
        <Topbar
          breadcrumb={breadcrumb}
          theme={theme}
          onToggleTheme={toggleTheme}
          onOpenFeedback={() => setFeedbackOpen(true)}
        />
        <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
          {view === "new" || view === "chat" ? (
            <ChatWorkspace
              mode={view === "chat" ? "all" : "personal"}
              teamSpaceId={selectedTeamSpaceId ?? undefined}
              teamSpaceName={selectedTeamSpaceName || undefined}
              initialTeamSpaceFilterVersion={initialTeamSpaceFilterVersion}
              initialMode={view === "new" ? "empty" : "chat"}
              onOpenWorkspaceDetail={() => setView("personalSpaceDetail")}
              onOpenTeamSpaces={openTeamSpaces}
              onOpenTeamDetail={openTeamDetailById}
              onBreadcrumbChange={setChatBreadcrumb}
              me={auth.me}
            />
          ) : view === "personalSpace" || view === "personalSpaceDetail" || view === "workspace" ? (
            <WorkspacePage onOpenSessions={() => setView("chat")} />
          ) : view === "teamSpaces" ? (
            <TeamSpacesPage
              onOpenChat={openTeamChat}
              onOpenDetail={openTeamDetail}
            />
          ) : view === "teamSpaceChat" && selectedTeamSpaceId ? (
            <ChatWorkspace
              mode="team"
              teamSpaceId={selectedTeamSpaceId}
              teamSpaceName={selectedTeamSpaceName || "团队空间"}
              onOpenWorkspaceDetail={() => setView("teamSpaceDetail")}
              onOpenTeamSpaces={openTeamSpaces}
              onOpenTeamDetail={openTeamDetailById}
              onBreadcrumbChange={setChatBreadcrumb}
              me={auth.me}
            />
          ) : view === "teamSpaceDetail" && selectedTeamSpaceId ? (
            <TeamSpaceDetailPage
              spaceId={selectedTeamSpaceId}
              spaceName={selectedTeamSpaceName || undefined}
              onOpenSessions={openSelectedTeamChat}
              onOpenTeamSpaces={openTeamSpaces}
            />
          ) : view === "agents" ? (
            <AgentsPage me={auth.me} />
          ) : view === "feedback" && auth.me.role !== "user" ? (
            <FeedbackAdminPage />
          ) : view === "skills" && auth.me.role !== "user" ? (
            <SkillsPage />
          ) : view === "loginWhitelist" && auth.me.role === "super" ? (
            <LoginWhitelistPage />
          ) : view === "usage" && auth.me.role !== "user" ? (
            <UsageAnalyticsPage />
          ) : (
            <TeamSpacesPage
              onOpenChat={openTeamChat}
              onOpenDetail={openTeamDetail}
            />
          )}
        </div>
      </div>
      <FeedbackDialog open={feedbackOpen} onClose={() => setFeedbackOpen(false)} />
    </div>
  );
}
