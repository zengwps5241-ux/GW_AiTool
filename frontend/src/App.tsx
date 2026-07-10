// 应用根组件：鉴权门 + 主题切换 + 视图路由
// 导航锁定 SidebarVariantA（分组侧边栏）；业务页面：对话/业务地图/营销地图/拜访记录
import { useEffect, useState, useCallback } from "react";
import { api } from "@/api/client";
import type { Project, TeamSpace, ThemeMode, UserMe, ViewName } from "@/types";
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
import BusinessMapPage from "@/pages/BusinessMapPage";
import MarketingMapPage from "@/pages/MarketingMapPage";
import VisitRecordsPage from "@/pages/VisitRecordsPage";
import UserApprovalPage from "@/pages/UserApprovalPage";
import OrganizationPage from "@/pages/OrganizationPage";
import SidebarVariantA from "@/components/SidebarVariantA";
import Topbar, { type BreadcrumbItem } from "@/components/Topbar";
import FeedbackDialog from "@/components/FeedbackDialog";
import ProjectSelector from "@/components/ProjectSelector";
import PendingDraftsBadge from "@/components/PendingDraftsBadge";

type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "logged_in"; me: UserMe };

const THEME_KEY = "goktech.theme";
const SIDEBAR_KEY = "goktech.sidebar_collapsed";

export default function App() {
  const [auth, setAuth] = useState<AuthState>({ status: "loading" });
  const [view, setView] = useState<ViewName>("chat");
  const [selectedTeamSpaceId, setSelectedTeamSpaceId] = useState<number | null>(null);
  const [selectedTeamSpaceName, setSelectedTeamSpaceName] = useState<string | null>(null);
  const [chatBreadcrumb, setChatBreadcrumb] = useState<BreadcrumbItem[]>(["对话"]);
  const [initialTeamSpaceFilterVersion, setInitialTeamSpaceFilterVersion] = useState(0);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  // 全局选中项目（M1.3.9）：业务地图/营销地图/拜访记录/对话 共享
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  /** 待采纳徽标"跳回原对话"：要打开的会话 id（M4.4.5） */
  const [focusSessionId, setFocusSessionId] = useState<string | null>(null);
  const [theme, setTheme] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem(THEME_KEY);
    return saved === "dark" ? "dark" : "light";
  });
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    return localStorage.getItem(SIDEBAR_KEY) === "1";
  });

  // 同步主题到 <html data-theme="...">
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  // 真实鉴权逻辑：拉取当前用户，未登录则显示登录页
  useEffect(() => {
    let alive = true;
    api
      .me()
      .then((me) => {
        if (alive) setAuth({ status: "logged_in", me });
      })
      .catch(() => {
        if (alive) setAuth({ status: "anonymous" });
      });
    return () => {
      alive = false;
    };
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // 忽略
    }
    setAuth({ status: "anonymous" });
  }, []);

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
      setChatBreadcrumb(["对话"]);
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
    return <LoginPage />;
  }

  // 已登录:主壳布局

  // 已登录主壳：导航锁定 SidebarVariantA（分组侧边栏）
  const sidebarProps = {
    current: view,
    onNav: handleNav,
    collapsed,
    onToggle: () => setCollapsed((c) => !c),
    user: auth.me,
    onLogout: handleLogout,
  };

  const breadcrumb: BreadcrumbItem[] =
    view === "businessMap"
      ? ["业务地图"]
      : view === "marketingMap"
      ? ["营销地图"]
      : view === "visitRecords"
      ? ["拜访记录"]
      : view === "userApproval"
      ? ["设置", "用户管理"]
      : view === "organization"
      ? ["设置", "组织架构"]
      : view === "personalSpace"
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
      : ["对话"];

  const renderPage = () => {
    // 业务地图页面（M4.1）：消费全局 selectedProject
    if (view === "businessMap")
      return (
        <BusinessMapPage
          project={selectedProject}
          onOpenVisitRecords={() => setView("visitRecords")}
        />
      );
    if (view === "marketingMap")
      return <MarketingMapPage project={selectedProject} />;
    if (view === "visitRecords") return <VisitRecordsPage />;

    // 用户审批页面（管理员）
    if (view === "userApproval" && auth.me.role !== "user") return <UserApprovalPage />;

    // 组织架构管理页（管理员）
    if (view === "organization" && auth.me.role !== "user") return <OrganizationPage />;

    if (view === "new" || view === "chat") {
      return (
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
          selectedProject={selectedProject}
          focusSessionId={focusSessionId}
          onFocusSessionConsumed={() => setFocusSessionId(null)}
          me={auth.me}
        />
      );
    }
    if (view === "personalSpace" || view === "personalSpaceDetail" || view === "workspace") {
      return <WorkspacePage onOpenSessions={() => setView("chat")} />;
    }
    if (view === "teamSpaces") {
      return (
        <TeamSpacesPage
          onOpenChat={openTeamChat}
          onOpenDetail={openTeamDetail}
        />
      );
    }
    if (view === "teamSpaceChat" && selectedTeamSpaceId) {
      return (
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
      );
    }
    if (view === "teamSpaceDetail" && selectedTeamSpaceId) {
      return (
        <TeamSpaceDetailPage
          spaceId={selectedTeamSpaceId}
          spaceName={selectedTeamSpaceName || undefined}
          onOpenSessions={openSelectedTeamChat}
          onOpenTeamSpaces={openTeamSpaces}
        />
      );
    }
    if (view === "agents") return <AgentsPage me={auth.me} />;
    if (view === "feedback" && auth.me.role !== "user") return <FeedbackAdminPage />;
    if (view === "skills" && auth.me.role !== "user") return <SkillsPage />;
    if (view === "loginWhitelist" && auth.me.role === "super") return <LoginWhitelistPage />;
    if (view === "usage" && auth.me.role !== "user") return <UsageAnalyticsPage />;

    return (
      <TeamSpacesPage
        onOpenChat={openTeamChat}
        onOpenDetail={openTeamDetail}
      />
    );
  };

  return (
    <div style={{ height: "100%", display: "flex", background: "var(--bg)" }}>
      <SidebarVariantA {...sidebarProps} />
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
          projectSlot={
            <ProjectSelector
              compact
              value={selectedProject?.id ?? null}
              onChange={setSelectedProject}
            />
          }
          badgeSlot={
            <PendingDraftsBadge
              project={selectedProject}
              onJumpToChat={(sid) => {
                setFocusSessionId(sid);
                setView("chat");
              }}
            />
          }
        />
        <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
          {renderPage()}
        </div>
      </div>
      <FeedbackDialog open={feedbackOpen} onClose={() => setFeedbackOpen(false)} />
    </div>
  );
}
