// 通用 fetch 封装：所有调用都带 credentials: "same-origin"
import type {
  Agent,
  AgentCommand,
  BusinessMapObject,
  BusinessMapObjectInput,
  BusinessMapVersion,
  VersionDiff,
  Category,
  ChatModelSelection,
  ChatEvent,
  AdoptResult,
  ConversionTask,
  EvidenceSource,
  EvidenceSourceInput,
  Customer,
  CustomerInput,
  PendingReviewItem,
  FeedbackIssueCreated,
  FeedbackIssueDetail,
  FeedbackIssueList,
  FileNode,
  FiveDimHealthOut,
  BusinessMapDraft,
  KnowledgeBase,
  KnowledgeBaseInput,
  MethodologyCategory,
  MethodologyItem,
  MethodologyItemInput,
  MenuNode,
  MenuAdmin,
  MenuAdminTree,
  MenuInput,
  MenuUpdateInput,
  MenuSortItem,
  Role,
  RoleInput,
  RoleUpdateInput,
  AdminUser,
  AdminUserCreateInput,
  AdminUserFilter,
  AuditLog,
  AuditLogFilter,
  KnowledgeFragment,
  KnowledgeFragmentInput,
  LoginWhitelistConfig,
  LoginWhitelistDepartment,
  LoginWhitelistDepartmentSearchItem,
  LoginWhitelistUser,
  ModelSettings,
  Organization,
  OrganizationImportResponse,
  OrganizationImportRow,
  OrganizationInput,
  OrganizationTreeNode,
  Plugin,
  PreAnalysis,
  PreAnalysisInput,
  ProcurementTimeline,
  ProcurementTimelineInput,
  Project,
  ProjectDepartmentAccess,
  ProjectInput,
  ProjectMember,
  RunEvent,
  RunningSessionState,
  Session,
  Skill,
  StanceChangeResult,
  DisambiguationCandidate,
  DisambiguationResolveInput,
  VisitRecord,
  VisitRecordInput,
  StakeholderCard,
  StakeholderCardInput,
  StakeholderGraph,
  StakeholderRelation,
  StakeholderRelationInput,
  TalkScript,
  TalkScriptInput,
  TeamMemberRole,
  TeamSpace,
  TeamSpaceMember,
  TeamSpaceMemberSearchItem,
  PublicAssetsOut,
  UserSearchItem,
  UploadedFile,
  UploadBatch,
  UploadTask,
  UploadTaskCreateItem,
  UsageSummary,
  UserMe,
  WorkspaceKind,
  WorkspaceNode,
  WorkspaceTask,
} from "@/types";
import { uploadedFilesFromBatch } from "@/lib/uploads";

let redirectingToLogin = false;

function redirectToLogin() {
  if (redirectingToLogin || typeof window === "undefined") return;
  redirectingToLogin = true;
  // 新方案:登录页就是当前页,无需跳转,App.tsx 会自行渲染二维码登录页
}

function unauthorizedError(): Error & { code?: string } {
  const err = new Error("unauthorized") as Error & { code?: string };
  err.code = "unauthorized";
  return err;
}

function handleUnauthorizedResponse(res: Response) {
  if (res.status !== 401) return;
  redirectToLogin();
  throw unauthorizedError();
}

export async function request<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(url, {
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
  handleUnauthorizedResponse(res);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    const err = new Error(`HTTP ${res.status}: ${text || res.statusText}`) as Error & {
      status?: number;
      responseText?: string;
    };
    err.status = res.status;
    err.responseText = text;
    throw err;
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

type SessionQuery = {
  workspace_kind?: WorkspaceKind | "all";
  team_space_id?: number | null;
  agent_id?: number | null;
  /** M7.1：按选中项目过滤会话列表。传入则仅返回该项目会话；省略/undefined 返回全部（含自由对话会话） */
  project_id?: number | null;
  limit?: number;
  offset?: number;
  mine_only?: boolean;
};

type CreateSessionPayload = {
  agent_id?: number | null;
  workspace_kind?: WorkspaceKind;
  team_space_id?: number | null;
  is_shared?: boolean;
  /** 项目级会话绑定（M3.4.2）：传入则后端自动加载项目 Agent（含 Skill/Plugin） */
  project_id?: number | null;
};

type UploadTaskFileOptions = {
  onProgress?: (percent: number) => void;
  url?: string;
};

function sessionQueryString(params?: SessionQuery) {
  if (!params) return "";
  const qs = new URLSearchParams();
  if (params.workspace_kind) qs.set("workspace_kind", params.workspace_kind);
  if (params.team_space_id !== undefined && params.team_space_id !== null) {
    qs.set("team_space_id", String(params.team_space_id));
  }
  if (params.agent_id !== undefined && params.agent_id !== null) {
    qs.set("agent_id", String(params.agent_id));
  }
  // M7.1：project_id 过滤（决策 #72）。undefined 不带参数→后端全量；
  // 传入 id→仅该项目会话（排除自由对话会话）。
  if (params.project_id !== undefined && params.project_id !== null) {
    qs.set("project_id", String(params.project_id));
  }
  if (params.limit !== undefined) qs.set("limit", String(params.limit));
  if (params.offset !== undefined) qs.set("offset", String(params.offset));
  if (params.mine_only !== undefined) qs.set("mine_only", String(params.mine_only));
  const query = qs.toString();
  return query ? `?${query}` : "";
}

export const api = {
  // 用户
  me: () => request<UserMe>("/api/me"),
  logout: () =>
    request<void>("/api/auth/logout", { method: "POST" }),

  // 菜单：当前用户可见菜单树（GET /api/menus，决策 #67 登录后一次性加载）
  getMenus: () => request<MenuNode[]>("/api/menus"),

  // 自建认证 API
  register: (data: { username?: string; phone?: string; password: string; display_name?: string }) =>
    request<{ success: boolean; message: string; user_id: number }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  login: (login: string, password: string) =>
    request<{ success: boolean }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ login, password }),
    }),

  // 管理员审批
  listPendingUsers: () =>
    request<Array<{
      id: number;
      username: string;
      phone: string | null;
      display_name: string | null;
      status: string;
      registration_source: string;
      created_at: string | null;
    }>>("/api/admin/pending-users"),

  approveUser: (userId: number, action: "approve" | "reject", reason?: string) =>
    request<{ success: boolean; user_id: number; status: string }>(`/api/admin/approve-user/${userId}`, {
      method: "POST",
      body: JSON.stringify({ action, reason }),
    }),

  // 组织架构管理（自建三级：公司→部门→小组）
  listOrganizations: () =>
    request<Organization[]>("/api/admin/organizations"),
  organizationTree: () =>
    request<OrganizationTreeNode[]>("/api/admin/organizations/tree"),
  createOrganization: (data: OrganizationInput) =>
    request<Organization>("/api/admin/organizations", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateOrganization: (id: number, data: Partial<OrganizationInput>) =>
    request<Organization>(`/api/admin/organizations/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteOrganization: (id: number) =>
    request<void>(`/api/admin/organizations/${id}`, { method: "DELETE" }),
  addOrganizationMember: (orgId: number, data: { user_id: number; position_title?: string; is_primary?: boolean }) =>
    request<void>(`/api/admin/organizations/${orgId}/members`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  removeOrganizationMember: (orgId: number, userId: number) =>
    request<void>(`/api/admin/organizations/${orgId}/members/${userId}`, {
      method: "DELETE",
    }),
  importOrganizations: (rows: OrganizationImportRow[]) =>
    request<OrganizationImportResponse>("/api/admin/organizations/import", {
      method: "POST",
      body: JSON.stringify(rows),
    }),
  importOrganizationsCsv: (content: string) =>
    request<OrganizationImportResponse>("/api/admin/organizations/import-csv", {
      method: "POST",
      body: JSON.stringify({ content, content_type: "csv" }),
    }),

  // DEPRECATED: 企微登录模式配置，保留以备未来扩展
  wechatWorkConfig: () =>
    request<{ mode: string }>("/api/auth/wechat-work/config"),

  // DEPRECATED: 企微自建二维码登录
  wechatWorkQrCodeConfig: () =>
    request<{
      appid: string;
      redirect_uri: string;
      state: string;
      agentid: string;
      scope: string;
    }>("/api/auth/wechat-work/qrcode-config"),

  wechatWorkPollCode: (state: string) =>
    request<{ code: string } | undefined>(
      `/api/auth/wechat-work/poll-code?state=${encodeURIComponent(state)}`,
    ),

  wechatWorkLoginByCode: (code: string) =>
    request<{ success: boolean }>("/api/auth/wechat-work/login-by-code", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),

  // 会话
  sessions: (params?: SessionQuery) =>
    request<Session[]>(`/api/sessions${sessionQueryString(params)}`),
  createSession: (payload: number | null | CreateSessionPayload) => {
    const body =
      typeof payload === "number" || payload === null
        ? { agent_id: payload }
        : payload;
    return request<Session>("/api/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  deleteSession: (id: string) =>
    request<void>(`/api/sessions/${id}`, { method: "DELETE" }),

  // 团队空间
  teamSpaces: () => request<TeamSpace[]>("/api/team-spaces"),
  createTeamSpace: (payload: { name: string; description?: string | null }) =>
    request<TeamSpace>("/api/team-spaces", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  teamSpace: (spaceId: number) =>
    request<TeamSpace>(`/api/team-spaces/${encodeURIComponent(spaceId)}`),
  teamSpaceMembers: (spaceId: number) =>
    request<TeamSpaceMember[]>(
      `/api/team-spaces/${encodeURIComponent(spaceId)}/members`,
    ),
  searchTeamSpaceMemberCandidates: (spaceId: number, keyword: string) =>
    request<TeamSpaceMemberSearchItem[]>(
      `/api/team-spaces/${encodeURIComponent(spaceId)}/members/search?keyword=${encodeURIComponent(keyword)}`,
    ),
  addTeamSpaceMember: (
    spaceId: number,
    payload: { user_id: number; role: TeamMemberRole },
  ) =>
    request<{ id: number; user_id: number; role: TeamMemberRole }>(
      `/api/team-spaces/${encodeURIComponent(spaceId)}/members`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
  updateTeamSpaceMember: (
    spaceId: number,
    memberId: number,
    payload: { role: TeamMemberRole },
  ) =>
    request<TeamSpaceMember>(
      `/api/team-spaces/${encodeURIComponent(spaceId)}/members/${encodeURIComponent(memberId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    ),
  removeTeamSpaceMember: (spaceId: number, memberId: number) =>
    request<void>(
      `/api/team-spaces/${encodeURIComponent(spaceId)}/members/${encodeURIComponent(memberId)}`,
      { method: "DELETE" },
    ),
  transferTeamSpaceOwner: (spaceId: number, userId: number) =>
    request<TeamSpace>(`/api/team-spaces/${encodeURIComponent(spaceId)}/owner`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }),
  leaveTeamSpace: (spaceId: number) =>
    request<void>(`/api/team-spaces/${encodeURIComponent(spaceId)}/leave`, {
      method: "POST",
    }),
  lockTeamSpace: (spaceId: number, note?: string | null) =>
    request<TeamSpace>(`/api/team-spaces/${encodeURIComponent(spaceId)}/lock`, {
      method: "POST",
      body: JSON.stringify({ note: note || null }),
    }),
  unlockTeamSpace: (spaceId: number) =>
    request<TeamSpace>(`/api/team-spaces/${encodeURIComponent(spaceId)}/lock`, {
      method: "DELETE",
    }),
  // ─── 对象公开机制（M5.5.3，§2.6 / §5.x / §6.3）─────────────────
  listPublicAssets: () => request<PublicAssetsOut>("/api/team-spaces/public-assets"),
  listSharedWithMe: () =>
    request<PublicAssetsOut>("/api/team-spaces/shared-with-me"),
  searchUsers: (keyword: string) =>
    request<UserSearchItem[]>(
      `/api/team-spaces/users/search?keyword=${encodeURIComponent(keyword)}`,
    ),
  // ─── 方法论库（§2.6 / §6.3，admin 维护，用户只读）─────────────
  listMethodology: (category?: MethodologyCategory) =>
    request<MethodologyItem[]>(
      `/api/team-spaces/methodology-library${category ? `?category=${category}` : ""}`,
    ),
  createMethodology: (payload: MethodologyItemInput) =>
    request<MethodologyItem>("/api/team-spaces/methodology-library", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateMethodology: (id: number, payload: Partial<MethodologyItemInput>) =>
    request<MethodologyItem>(`/api/team-spaces/methodology-library/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  deleteMethodology: (id: number) =>
    request<void>(`/api/team-spaces/methodology-library/${id}`, {
      method: "DELETE",
    }),
  updateSessionTitle: (id: string, title: string) =>
    request<Session>(`/api/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  sessionMessages: (id: string) =>
    request<ChatEvent[]>(`/api/sessions/${id}/messages`),
  /** 对话「标记为有价值」→ 落盘个人空间知识片段（§2.6 line157）*/
  markValuable: (sessionId: string, body: KnowledgeFragmentInput) =>
    request<KnowledgeFragment>(
      `/api/sessions/${encodeURIComponent(sessionId)}/knowledge-fragments`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  sessionRunning: (id: string) =>
    request<RunningSessionState>(`/api/sessions/${id}/running`),
  stopSession: (id: string) =>
    request<{ stopped: boolean }>(`/api/sessions/${id}/stop`, {
      method: "POST",
    }),
  modelSettings: () => request<ModelSettings>("/api/model-settings"),

  // 智能体
  agents: () => request<Agent[]>("/api/agents"),
  createAgent: (data: {
    name: string;
    code: string;
    system_prompt: string | null;
    skills: string;
    plugins: string;
    category_id: number | null;
  }) =>
    request<Agent>("/api/agents", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateAgent: (
    id: number,
    data: Partial<{
      name: string;
      system_prompt: string | null;
      skills: string;
      plugins: string;
      category_id: number | null;
    }>,
  ) =>
    request<Agent>(`/api/agents/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteAgent: (id: number) =>
    request<void>(`/api/agents/${id}`, { method: "DELETE" }),

  /** 重新初始化智能体工作目录(刷新 plugins/skills/CLAUDE.md,保留 SDK 产物) */
  reinitAgent: (id: number) =>
    request<Agent>(`/api/agents/${id}/reinit`, { method: "POST" }),
  agentCommands: (id: number) =>
    request<AgentCommand[]>(`/api/agents/${id}/commands`),

  // 技能
  skills: () => request<Skill[]>("/api/skills"),

  // 插件(读取 claude_data_dir/plugins 下的本地插件清单)
  plugins: () => request<Plugin[]>("/api/plugins"),

  // 问题反馈
  createFeedbackIssue: async (data: {
    title: string;
    description: string;
    images: File[];
  }) => {
    const form = new FormData();
    form.append("title", data.title);
    form.append("description", data.description);
    data.images.forEach((image) => form.append("images", image, image.name));
    const res = await fetch("/api/feedback/issues", {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    handleUnauthorizedResponse(res);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }
    return res.json() as Promise<FeedbackIssueCreated>;
  },

  adminFeedbackIssues: (page: number, pageSize: number) =>
    request<FeedbackIssueList>(
      `/api/admin/feedback/issues?page=${encodeURIComponent(page)}&page_size=${encodeURIComponent(pageSize)}`,
    ),

  adminFeedbackIssue: (id: number) =>
    request<FeedbackIssueDetail>(`/api/admin/feedback/issues/${encodeURIComponent(id)}`),

  deleteFeedbackIssue: (id: number) =>
    request<void>(`/api/admin/feedback/issues/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  adminFeedbackAttachmentUrl: (id: number) =>
    `/api/admin/feedback/attachments/${encodeURIComponent(id)}`,

  // 登录白名单
  loginWhitelist: () =>
    request<LoginWhitelistConfig>("/api/admin/login-whitelist"),

  createLoginWhitelistUser: (name: string) =>
    request<LoginWhitelistUser>("/api/admin/login-whitelist/users", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  deleteLoginWhitelistUser: (id: number) =>
    request<void>(`/api/admin/login-whitelist/users/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  searchLoginWhitelistDepartments: (q: string) =>
    request<LoginWhitelistDepartmentSearchItem[]>(
      `/api/admin/login-whitelist/departments/search?q=${encodeURIComponent(q)}`,
    ),

  createLoginWhitelistDepartment: (departmentId: number) =>
    request<LoginWhitelistDepartment>("/api/admin/login-whitelist/departments", {
      method: "POST",
      body: JSON.stringify({ department_id: departmentId }),
    }),

  deleteLoginWhitelistDepartment: (id: number) =>
    request<void>(
      `/api/admin/login-whitelist/departments/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),

  // 文件上传
  // 注意:multipart/form-data 不能手动设置 Content-Type,
  // 否则浏览器无法自动注入 boundary,服务端会解析失败。
  uploadFiles: async (files: File[]): Promise<UploadedFile[]> => {
    const batch = await api.uploadFilesToWorkspace(files, {
      targetDir: "uploads",
      relativePaths: files.map((f) => f.name),
    });
    return uploadedFilesFromBatch(batch);
  },

  uploadFilesToWorkspace: (
    files: File[],
    opts: {
      targetDir: string;
      relativePaths?: string[];
      onProgress?: (percent: number) => void;
    },
  ) =>
    new Promise<UploadBatch>((resolve, reject) => {
      const form = new FormData();
      files.forEach((file) => form.append("files", file, file.name));
      form.append("target_dir", opts.targetDir);
      form.append(
        "relative_paths",
        JSON.stringify(opts.relativePaths ?? files.map((f) => f.name)),
      );
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/uploads");
      xhr.withCredentials = true;
      xhr.upload.onprogress = (evt) => {
        if (evt.lengthComputable && opts.onProgress) {
          opts.onProgress(Math.round((evt.loaded / evt.total) * 100));
        }
      };
      xhr.onload = () => {
        if (xhr.status === 401) {
          redirectToLogin();
          reject(unauthorizedError());
          return;
        }
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(new Error(`HTTP ${xhr.status}: ${xhr.responseText || xhr.statusText}`));
          return;
        }
        resolve(JSON.parse(xhr.responseText) as UploadBatch);
      };
      xhr.onerror = () => reject(new Error("上传失败"));
      xhr.send(form);
    }),

  createUploadTasks: (targetDir: string, items: UploadTaskCreateItem[]) =>
    request<UploadTask[]>("/api/upload-tasks", {
      method: "POST",
      body: JSON.stringify({ target_dir: targetDir, items }),
    }),

  uploadTaskFile: (
    taskId: number,
    file: File,
    opts: UploadTaskFileOptions = {},
  ) =>
    new Promise<UploadTask>((resolve, reject) => {
      const form = new FormData();
      form.append("file", file, file.name);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", opts.url ?? `/api/upload-tasks/${taskId}/file`);
      xhr.withCredentials = true;
      xhr.upload.onprogress = (evt) => {
        if (evt.lengthComputable && opts.onProgress) {
          opts.onProgress(Math.round((evt.loaded / evt.total) * 100));
        }
      };
      xhr.onload = () => {
        if (xhr.status === 401) {
          redirectToLogin();
          reject(unauthorizedError());
          return;
        }
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(new Error(`HTTP ${xhr.status}: ${xhr.responseText || xhr.statusText}`));
          return;
        }
        resolve(JSON.parse(xhr.responseText) as UploadTask);
      };
      xhr.onerror = () => reject(new Error("上传失败"));
      xhr.send(form);
    }),

  updateUploadTaskProgress: (taskId: number, progress: number) =>
    request<UploadTask>(`/api/upload-tasks/${taskId}/progress`, {
      method: "PATCH",
      body: JSON.stringify({ progress }),
    }),

  abandonUploadTasks: (ids: number[], errorMessage?: string) =>
    request<UploadTask[]>("/api/upload-tasks/abandon", {
      method: "POST",
      body: JSON.stringify({ ids, error_message: errorMessage }),
    }),

  // 个人空间文件树
  workspaceTree: () => request<WorkspaceNode[]>("/api/workspace/tree"),
  // 删除个人空间中的文件或目录(目录递归删除)
  deleteWorkspaceItem: (path: string) =>
    request<void>(
      `/api/workspace/file?path=${encodeURIComponent(path)}`,
      { method: "DELETE" },
    ),

  // 下载 URL:文件直发字节,目录由后端流式打包为 zip
  workspaceDownloadUrl: (path: string) =>
    `/api/workspace/download?path=${encodeURIComponent(path)}`,

  // 下载 Office/PDF 转换后的 Markdown 提取目录 zip
  workspaceMarkdownDownloadUrl: (path: string) =>
    `/api/workspace/download-markdown?path=${encodeURIComponent(path)}`,

  // 预览 URL:文本、媒体、转换后 Markdown 均统一从这里读取
  workspacePreviewUrl: (path: string) =>
    `/api/workspace/preview?path=${encodeURIComponent(path)}`,

  workspaceOfficePreviewUrl: (path: string) =>
    `/api/workspace/office-preview?path=${encodeURIComponent(path)}`,

  workspaceMarkdownPreviewUrl: (path: string) =>
    `/api/workspace/markdown-preview?path=${encodeURIComponent(path)}`,

  workspaceSaveContent: (path: string, content: string) =>
    request<{
      path: string;
      content: string;
      size: number;
      mtime?: number;
    }>("/api/workspace/content", {
      method: "PUT",
      body: JSON.stringify({ path, content }),
    }),

  workspaceCreateItem: (path: string, kind: "file" | "dir", content = "") =>
    request<{ path: string }>("/api/workspace/file", {
      method: "POST",
      body: JSON.stringify({ path, kind, content }),
    }),

  workspaceRenameItem: (path: string, newName: string) =>
    request<{ path: string }>("/api/workspace/file/rename", {
      method: "PATCH",
      body: JSON.stringify({ path, new_name: newName }),
    }),

  workspaceMoveItem: (path: string, targetDir: string) =>
    request<{ path: string }>("/api/workspace/file/move", {
      method: "PATCH",
      body: JSON.stringify({ path, target_dir: targetDir }),
    }),

  // 转换任务
  conversionTasks: (limit?: number, offset?: number) => {
    const qs = new URLSearchParams();
    if (limit !== undefined) qs.set("limit", String(limit));
    if (offset !== undefined) qs.set("offset", String(offset));
    const query = qs.toString();
    return request<ConversionTask[]>(
      `/api/conversion-tasks${query ? "?" + query : ""}`,
    );
  },

  workspaceTasks: (limit?: number, offset?: number) => {
    const qs = new URLSearchParams();
    if (limit !== undefined) qs.set("limit", String(limit));
    if (offset !== undefined) qs.set("offset", String(offset));
    const query = qs.toString();
    return request<WorkspaceTask[]>(
      `/api/workspace-tasks${query ? "?" + query : ""}`,
    );
  },

  retryConversion: (sourcePath: string) =>
    request<ConversionTask>("/api/conversion-tasks/retry", {
      method: "POST",
      body: JSON.stringify({ source_path: sourcePath }),
    }),

  // 分类管理
  categories: () => request<Category[]>("/api/admin/categories"),
  createCategory: (name: string) =>
    request<Category>("/api/admin/categories", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  renameCategory: (id: number, name: string) =>
    request<Category>(`/api/admin/categories/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  deleteCategory: (id: number) =>
    request<void>(`/api/admin/categories/${id}`, { method: "DELETE" }),

  // 管理员 — 技能上传(单独 fetch,不走 request 通用封装)
  adminUploadSkill: async (file: File, categoryId: number) => {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("category_id", String(categoryId));
    const res = await fetch("/api/admin/skills/upload", {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    handleUnauthorizedResponse(res);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }
    return res.json() as Promise<{ name: string; message: string }>;
  },

  adminDeleteSkill: (name: string, force?: boolean) =>
    request<void>(
      `/api/admin/skills/${encodeURIComponent(name)}${force ? "?force=true" : ""}`,
      { method: "DELETE" },
    ),

  adminUpdateSkillCategory: (name: string, categoryId: number) =>
    request<{ name: string; category_id: number }>(
      `/api/admin/skills/${encodeURIComponent(name)}/category`,
      {
        method: "PATCH",
        body: JSON.stringify({ category_id: categoryId }),
      },
    ),

  adminSkillFiles: (name: string) =>
    request<FileNode>(`/api/admin/skills/${encodeURIComponent(name)}/files`),

  adminSkillFileContent: async (name: string, path: string) => {
    const res = await fetch(
      `/api/admin/skills/${encodeURIComponent(name)}/files/${encodeURIComponent(path)}`,
      { credentials: "same-origin" },
    );
    handleUnauthorizedResponse(res);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }
    return res.text();
  },

  adminWriteSkillFile: (name: string, path: string, content: string) =>
    request<void>(
      `/api/admin/skills/${encodeURIComponent(name)}/files/${encodeURIComponent(path)}`,
      {
        method: "PUT",
        body: JSON.stringify({ content }),
      },
    ),

  adminCreateSkillFile: (name: string, path: string, content: string) =>
    request<void>(
      `/api/admin/skills/${encodeURIComponent(name)}/files`,
      {
        method: "POST",
        body: JSON.stringify({ path, content }),
      },
    ),

  adminDeleteSkillFile: (name: string, path: string) =>
    request<void>(
      `/api/admin/skills/${encodeURIComponent(name)}/files/${encodeURIComponent(path)}`,
      { method: "DELETE" },
    ),

  // 管理员 — 插件上传
  adminUploadPlugin: async (file: File, categoryId: number) => {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("category_id", String(categoryId));
    const res = await fetch("/api/admin/plugins/upload", {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    handleUnauthorizedResponse(res);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }
    return res.json() as Promise<{ name: string; message: string }>;
  },

  adminDeletePlugin: (name: string, force?: boolean) =>
    request<void>(
      `/api/admin/plugins/${encodeURIComponent(name)}${force ? "?force=true" : ""}`,
      { method: "DELETE" },
    ),

  adminUpdatePluginCategory: (path: string, categoryId: number) =>
    request<{ path: string; category_id: number }>(
      `/api/admin/plugins/${encodeURIComponent(path)}/category`,
      {
        method: "PATCH",
        body: JSON.stringify({ category_id: categoryId }),
      },
    ),

  adminPluginFiles: (name: string) =>
    request<FileNode>(`/api/admin/plugins/${encodeURIComponent(name)}/files`),

  adminPluginFileContent: async (name: string, path: string) => {
    const res = await fetch(
      `/api/admin/plugins/${encodeURIComponent(name)}/files/${encodeURIComponent(path)}`,
      { credentials: "same-origin" },
    );
    handleUnauthorizedResponse(res);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }
    return res.text();
  },

  adminUsageSummary: (params: {
    range?: "today" | "7d" | "30d" | "custom";
    start?: string;
    end?: string;
    user?: string;
    department?: string;
  } = {}) => {
    const query = new URLSearchParams();
    if (params.range) query.set("range", params.range);
    if (params.start) query.set("start", params.start);
    if (params.end) query.set("end", params.end);
    if (params.user) query.set("user", params.user);
    if (params.department) query.set("department", params.department);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<UsageSummary>(`/api/admin/usage/summary${suffix}`);
  },

  adminUsageUsers: (q: string) =>
    request<{ display_name: string; department: string | null; username: string }[]>(
      "/api/admin/usage/users?" + new URLSearchParams({ q }),
    ),

  adminUsageDepartments: (q: string) =>
    request<string[]>("/api/admin/usage/departments?" + new URLSearchParams({ q })),

  // ─── 客户管理（M1.3.5）─────────────────────────────────────
  listCustomers: () => request<Customer[]>("/api/customers"),
  getCustomer: (id: number) => request<Customer>(`/api/customers/${id}`),
  createCustomer: (data: CustomerInput) =>
    request<Customer>("/api/customers", { method: "POST", body: JSON.stringify(data) }),
  updateCustomer: (id: number, data: Partial<CustomerInput>) =>
    request<Customer>(`/api/customers/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteCustomer: (id: number) =>
    request<void>(`/api/customers/${id}`, { method: "DELETE" }),

  // ─── 项目管理（M1.3.6）─────────────────────────────────────
  listProjects: () => request<Project[]>("/api/projects"),
  getProject: (id: number) => request<Project>(`/api/projects/${id}`),
  createProject: (data: ProjectInput) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(data) }),
  updateProject: (id: number, data: Partial<ProjectInput>) =>
    request<Project>(`/api/projects/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteProject: (id: number) =>
    request<void>(`/api/projects/${id}`, { method: "DELETE" }),

  listProjectMembers: (projectId: number) =>
    request<ProjectMember[]>(`/api/projects/${projectId}/members`),
  addProjectMember: (projectId: number, data: { user_id: number; role?: "owner" | "deputy" }) =>
    request<ProjectMember>(`/api/projects/${projectId}/members`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  removeProjectMember: (projectId: number, userId: number) =>
    request<void>(`/api/projects/${projectId}/members/${userId}`, { method: "DELETE" }),

  listProjectDeptAccess: (projectId: number) =>
    request<ProjectDepartmentAccess[]>(`/api/projects/${projectId}/department-access`),
  grantProjectDeptAccess: (projectId: number, organizationId: number) =>
    request<ProjectDepartmentAccess>(`/api/projects/${projectId}/department-access`, {
      method: "POST",
      body: JSON.stringify({ organization_id: organizationId }),
    }),
  revokeProjectDeptAccess: (projectId: number, organizationId: number) =>
    request<void>(`/api/projects/${projectId}/department-access/${organizationId}`, {
      method: "DELETE",
    }),

  // ─── 采纳草稿（M2.4 统一派发器 / M3.1.3 衔接）─────────────────
  adoptDraft: (projectId: number, entityType: string, draftId: number) =>
    request<AdoptResult>(`/api/projects/${projectId}/adopt`, {
      method: "POST",
      body: JSON.stringify({ entity_type: entityType, draft_id: draftId }),
    }),

  // ─── 待审批列表 + Owner 审批（M2.4 / M4.4.4 对话 Banner）─────────
  /** 待审批列表（跨模块聚合 pending_review，§3.4） */
  listPendingReviews: (projectId: number, entityType?: string) => {
    const qs = new URLSearchParams();
    if (entityType) qs.set("entity_type", entityType);
    const query = qs.toString();
    return request<PendingReviewItem[]>(
      `/api/projects/${projectId}/pending-reviews${query ? "?" + query : ""}`,
    );
  },
  /** Owner 通过待审批项（§7.3 发布） */
  approveReview: (
    projectId: number,
    entityType: string,
    entityId: number,
  ) =>
    request<PendingReviewItem>(
      `/api/projects/${projectId}/reviews/${entityType}/${entityId}/approve`,
      { method: "POST" },
    ),
  /** Owner 驳回待审批项（§3.4 退回，可选意见） */
  rejectReview: (
    projectId: number,
    entityType: string,
    entityId: number,
    comment?: string,
  ) =>
    request<PendingReviewItem>(
      `/api/projects/${projectId}/reviews/${entityType}/${entityId}/reject`,
      {
        method: "POST",
        body: JSON.stringify(comment != null ? { comment } : {}),
      },
    ),

  // ─── 业务地图（M4.1 / M2.1 后端就绪）─────────────────────────
  listBusinessMapObjects: (
    projectId: number,
    params?: {
      level?: string;
      map_type?: string;
      review_status?: string;
      include_drafts?: boolean;
    },
  ) => {
    const qs = new URLSearchParams();
    if (params?.level) qs.set("level", params.level);
    if (params?.map_type) qs.set("map_type", params.map_type);
    if (params?.review_status) qs.set("review_status", params.review_status);
    if (params?.include_drafts) qs.set("include_drafts", "true");
    const query = qs.toString();
    return request<BusinessMapObject[]>(
      `/api/projects/${projectId}/business-map/objects${query ? "?" + query : ""}`,
    );
  },
  getBusinessMapObject: (projectId: number, objectId: number) =>
    request<BusinessMapObject>(
      `/api/projects/${projectId}/business-map/objects/${objectId}`,
    ),
  createBusinessMapObject: (projectId: number, data: BusinessMapObjectInput) =>
    request<BusinessMapObject>(
      `/api/projects/${projectId}/business-map/objects`,
      { method: "POST", body: JSON.stringify(data) },
    ),
  updateBusinessMapObject: (
    projectId: number,
    objectId: number,
    data: Partial<BusinessMapObjectInput>,
  ) =>
    request<BusinessMapObject>(
      `/api/projects/${projectId}/business-map/objects/${objectId}`,
      { method: "PUT", body: JSON.stringify(data) },
    ),
  deleteBusinessMapObject: (projectId: number, objectId: number) =>
    request<void>(
      `/api/projects/${projectId}/business-map/objects/${objectId}`,
      { method: "DELETE" },
    ),

  getPreAnalysis: (projectId: number) =>
    request<PreAnalysis | null>(
      `/api/projects/${projectId}/business-map/pre-analysis`,
    ),
  upsertPreAnalysis: (projectId: number, data: PreAnalysisInput) =>
    request<PreAnalysis>(
      `/api/projects/${projectId}/business-map/pre-analysis`,
      { method: "PUT", body: JSON.stringify(data) },
    ),

  listBusinessMapVersions: (projectId: number) =>
    request<BusinessMapVersion[]>(
      `/api/projects/${projectId}/business-map/versions`,
    ),
  getBusinessMapVersion: (projectId: number, versionId: number) =>
    request<BusinessMapVersion>(
      `/api/projects/${projectId}/business-map/versions/${versionId}`,
    ),
  rollbackBusinessMapVersion: (projectId: number, versionId: number) =>
    request<BusinessMapVersion>(
      `/api/projects/${projectId}/business-map/versions/${versionId}/rollback`,
      { method: "POST" },
    ),
  diffBusinessMapVersion: (projectId: number, versionId: number) =>
    request<VersionDiff>(
      `/api/projects/${projectId}/business-map/versions/${versionId}/diff`,
    ),

  recomputeBusinessMapHealth: (projectId: number) =>
    request<FiveDimHealthOut[]>(
      `/api/projects/${projectId}/business-map/health/recompute`,
      { method: "POST" },
    ),
  computeBusinessMapNodeHealth: (projectId: number, objectId: number) =>
    request<FiveDimHealthOut>(
      `/api/projects/${projectId}/business-map/objects/${objectId}/health`,
      { method: "POST" },
    ),
  setBusinessMapNodeHealth: (
    projectId: number,
    objectId: number,
    fiveDimHealth: Record<string, unknown>,
  ) =>
    request<FiveDimHealthOut>(
      `/api/projects/${projectId}/business-map/objects/${objectId}/health`,
      { method: "PUT", body: JSON.stringify(fiveDimHealth) },
    ),

  // ─── 拜访/证据（M2.3 / M4.1.10 关联证据）─────────────────────
  listEvidence: (
    projectId: number,
    params?: {
      visit_id?: number;
      evidence_type?: string;
      strength?: string;
      source_role_id?: number;
      related_hypothesis_id?: number;
      review_status?: string;
      include_drafts?: boolean;
    },
  ) => {
    const qs = new URLSearchParams();
    if (params?.visit_id != null) qs.set("visit_id", String(params.visit_id));
    if (params?.evidence_type) qs.set("evidence_type", params.evidence_type);
    if (params?.strength) qs.set("strength", params.strength);
    if (params?.source_role_id != null) qs.set("source_role_id", String(params.source_role_id));
    if (params?.related_hypothesis_id != null) qs.set("related_hypothesis_id", String(params.related_hypothesis_id));
    if (params?.review_status) qs.set("review_status", params.review_status);
    if (params?.include_drafts) qs.set("include_drafts", "true");
    const query = qs.toString();
    return request<EvidenceSource[]>(
      `/api/projects/${projectId}/evidence-sources${query ? "?" + query : ""}`,
    );
  },
  createEvidence: (projectId: number, data: EvidenceSourceInput) =>
    request<EvidenceSource>(
      `/api/projects/${projectId}/evidence-sources`,
      { method: "POST", body: JSON.stringify(data) },
    ),
  updateEvidence: (
    projectId: number,
    evidenceId: number,
    data: Partial<EvidenceSourceInput>,
  ) =>
    request<EvidenceSource>(
      `/api/projects/${projectId}/evidence-sources/${evidenceId}`,
      { method: "PUT", body: JSON.stringify(data) },
    ),
  deleteEvidence: (projectId: number, evidenceId: number) =>
    request<void>(
      `/api/projects/${projectId}/evidence-sources/${evidenceId}`,
      { method: "DELETE" },
    ),

  // ─── 营销地图（M4.2 / M2.2 后端就绪）─────────────────────────
  listStakeholderCards: (
    projectId: number,
    params?: {
      department?: string;
      role_type?: string;
      stance?: string;
      review_status?: string;
      include_drafts?: boolean;
    },
  ) => {
    const qs = new URLSearchParams();
    if (params?.department) qs.set("department", params.department);
    if (params?.role_type) qs.set("role_type", params.role_type);
    if (params?.stance) qs.set("stance", params.stance);
    if (params?.review_status) qs.set("review_status", params.review_status);
    if (params?.include_drafts) qs.set("include_drafts", "true");
    const query = qs.toString();
    return request<StakeholderCard[]>(
      `/api/projects/${projectId}/stakeholder-cards${query ? "?" + query : ""}`,
    );
  },
  getStakeholderCard: (projectId: number, cardId: number) =>
    request<StakeholderCard>(
      `/api/projects/${projectId}/stakeholder-cards/${cardId}`,
    ),
  createStakeholderCard: (projectId: number, data: StakeholderCardInput) =>
    request<StakeholderCard>(
      `/api/projects/${projectId}/stakeholder-cards`,
      { method: "POST", body: JSON.stringify(data) },
    ),
  updateStakeholderCard: (
    projectId: number,
    cardId: number,
    data: Partial<StakeholderCardInput>,
  ) =>
    request<StakeholderCard>(
      `/api/projects/${projectId}/stakeholder-cards/${cardId}`,
      { method: "PUT", body: JSON.stringify(data) },
    ),
  deleteStakeholderCard: (projectId: number, cardId: number) =>
    request<void>(
      `/api/projects/${projectId}/stakeholder-cards/${cardId}`,
      { method: "DELETE" },
    ),
  addStanceChange: (
    projectId: number,
    cardId: number,
    data: { from: string; to: string; reason: string },
  ) =>
    request<StanceChangeResult>(
      `/api/projects/${projectId}/stakeholder-cards/${cardId}/stance-changes`,
      { method: "POST", body: JSON.stringify(data) },
    ),

  listStakeholderRelations: (projectId: number) =>
    request<StakeholderRelation[]>(
      `/api/projects/${projectId}/stakeholder-relations`,
    ),
  createStakeholderRelation: (
    projectId: number,
    data: StakeholderRelationInput,
  ) =>
    request<StakeholderRelation>(
      `/api/projects/${projectId}/stakeholder-relations`,
      { method: "POST", body: JSON.stringify(data) },
    ),
  deleteStakeholderRelation: (projectId: number, relationId: number) =>
    request<void>(
      `/api/projects/${projectId}/stakeholder-relations/${relationId}`,
      { method: "DELETE" },
    ),
  getStakeholderGraph: (projectId: number) =>
    request<StakeholderGraph>(
      `/api/projects/${projectId}/stakeholder-relations/graph`,
    ),

  // ─── 角色去重候选（M5.5.1 person_disambiguation）──────────────
  listDisambiguationCandidates: (projectId: number, status?: string) => {
    const qs = new URLSearchParams();
    if (status) qs.set("status", status);
    const query = qs.toString();
    return request<DisambiguationCandidate[]>(
      `/api/projects/${projectId}/disambiguation-candidates${query ? "?" + query : ""}`,
    );
  },
  resolveDisambiguationCandidate: (
    projectId: number,
    candidateId: number,
    data: DisambiguationResolveInput,
  ) =>
    request<DisambiguationCandidate>(
      `/api/projects/${projectId}/disambiguation-candidates/${candidateId}/resolve`,
      { method: "POST", body: JSON.stringify(data) },
    ),

  listTalkScripts: (
    projectId: number,
    params?: { role_type?: string; scenario?: string },
  ) => {
    const qs = new URLSearchParams();
    if (params?.role_type) qs.set("role_type", params.role_type);
    if (params?.scenario) qs.set("scenario", params.scenario);
    const query = qs.toString();
    return request<TalkScript[]>(
      `/api/projects/${projectId}/talk-scripts${query ? "?" + query : ""}`,
    );
  },
  createTalkScript: (projectId: number, data: TalkScriptInput) =>
    request<TalkScript>(
      `/api/projects/${projectId}/talk-scripts`,
      { method: "POST", body: JSON.stringify(data) },
    ),
  updateTalkScript: (
    projectId: number,
    scriptId: number,
    data: Partial<TalkScriptInput>,
  ) =>
    request<TalkScript>(
      `/api/projects/${projectId}/talk-scripts/${scriptId}`,
      { method: "PUT", body: JSON.stringify(data) },
    ),
  deleteTalkScript: (projectId: number, scriptId: number) =>
    request<void>(
      `/api/projects/${projectId}/talk-scripts/${scriptId}`,
      { method: "DELETE" },
    ),

  listKnowledgeBase: (
    projectId: number,
    params?: { category?: string },
  ) => {
    const qs = new URLSearchParams();
    if (params?.category) qs.set("category", params.category);
    const query = qs.toString();
    return request<KnowledgeBase[]>(
      `/api/projects/${projectId}/knowledge-base${query ? "?" + query : ""}`,
    );
  },
  createKnowledgeBase: (projectId: number, data: KnowledgeBaseInput) =>
    request<KnowledgeBase>(
      `/api/projects/${projectId}/knowledge-base`,
      { method: "POST", body: JSON.stringify(data) },
    ),
  updateKnowledgeBase: (
    projectId: number,
    kbId: number,
    data: Partial<KnowledgeBaseInput>,
  ) =>
    request<KnowledgeBase>(
      `/api/projects/${projectId}/knowledge-base/${kbId}`,
      { method: "PUT", body: JSON.stringify(data) },
    ),
  deleteKnowledgeBase: (projectId: number, kbId: number) =>
    request<void>(
      `/api/projects/${projectId}/knowledge-base/${kbId}`,
      { method: "DELETE" },
    ),

  // ─── 采购流程时间线（M4.2.5）──────────────────────────────────
  /** 读取项目采购时间线（未建返回 null，前端用五阶段默认模板渲染） */
  getProcurementTimeline: (projectId: number) =>
    request<ProcurementTimeline | null>(
      `/api/projects/${projectId}/procurement-timeline`,
    ),
  /** 创建或更新采购时间线（项目级单例，整体替换 stages） */
  upsertProcurementTimeline: (
    projectId: number,
    data: ProcurementTimelineInput,
  ) =>
    request<ProcurementTimeline>(
      `/api/projects/${projectId}/procurement-timeline`,
      { method: "PUT", body: JSON.stringify(data) },
    ),

  // ─── 待采纳草稿找回（M4.4.5 §7.1 第8条 徽标兜底）─────────────
  /** 业务地图当前 active 草稿（整图草稿单元，单个或 null） */
  getActiveBusinessMapDraft: (projectId: number) =>
    request<BusinessMapDraft | null>(
      `/api/projects/${projectId}/business-map/drafts`,
    ),
  /** 拜访记录列表（含草稿筛选；M4.3 全量复用） */
  listVisitRecords: (
    projectId: number,
    params?: {
      visit_type?: string;
      card_id?: number;
      review_status?: string;
      include_drafts?: boolean;
    },
  ) => {
    const qs = new URLSearchParams();
    if (params?.visit_type) qs.set("visit_type", params.visit_type);
    if (params?.card_id != null) qs.set("card_id", String(params.card_id));
    if (params?.review_status) qs.set("review_status", params.review_status);
    if (params?.include_drafts) qs.set("include_drafts", "true");
    const query = qs.toString();
    return request<VisitRecord[]>(
      `/api/projects/${projectId}/visit-records${query ? "?" + query : ""}`,
    );
  },
  createVisitRecord: (projectId: number, data: VisitRecordInput) =>
    request<VisitRecord>(
      `/api/projects/${projectId}/visit-records`,
      { method: "POST", body: JSON.stringify(data) },
    ),
  updateVisitRecord: (
    projectId: number,
    visitId: number,
    data: Partial<VisitRecordInput>,
  ) =>
    request<VisitRecord>(
      `/api/projects/${projectId}/visit-records/${visitId}`,
      { method: "PUT", body: JSON.stringify(data) },
    ),
  deleteVisitRecord: (projectId: number, visitId: number) =>
    request<void>(
      `/api/projects/${projectId}/visit-records/${visitId}`,
      { method: "DELETE" },
    ),

  // ─── 系统设置 · 用户管理（M6.4 后端，require_admin）──────────────
  /** 全量用户列表 + 筛选（role/status/organization_id/search） */
  listAdminUsers: (filter?: AdminUserFilter) => {
    const qs = new URLSearchParams();
    if (filter?.role) qs.set("role", filter.role);
    if (filter?.status) qs.set("status", filter.status);
    if (filter?.organization_id != null)
      qs.set("organization_id", String(filter.organization_id));
    if (filter?.search) qs.set("search", filter.search);
    const query = qs.toString();
    return request<AdminUser[]>(`/api/admin/users${query ? "?" + query : ""}`);
  },
  /** 管理员创建用户（跳过审批 status=active） */
  createAdminUser: (data: AdminUserCreateInput) =>
    request<AdminUser>("/api/admin/users", { method: "POST", body: JSON.stringify(data) }),
  /** 启用/禁用用户（不可禁自己） */
  updateUserStatus: (userId: number, status: "active" | "disabled") =>
    request<{ success: boolean; user_id: number; status: string }>(
      `/api/admin/users/${userId}/status`,
      { method: "PUT", body: JSON.stringify({ status }) },
    ),
  /** 管理员重置用户密码 */
  resetUserPassword: (userId: number, newPassword: string) =>
    request<{ success: boolean; user_id: number }>(
      `/api/admin/users/${userId}/reset-password`,
      { method: "POST", body: JSON.stringify({ new_password: newPassword }) },
    ),
  /** 修改用户角色（更新 User.role 为目标 Role.code） */
  assignUserRole: (userId: number, roleCode: string) =>
    request<{ user_id: number; role: string }>(
      `/api/admin/users/${userId}/role`,
      { method: "PUT", body: JSON.stringify({ role_code: roleCode }) },
    ),

  // ─── 系统设置 · 角色管理（M6.1 后端，require_admin）──────────────
  listRoles: () => request<Role[]>("/api/admin/roles"),
  createRole: (data: RoleInput) =>
    request<Role>("/api/admin/roles", { method: "POST", body: JSON.stringify(data) }),
  updateRole: (id: number, data: RoleUpdateInput) =>
    request<Role>(`/api/admin/roles/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteRole: (id: number) =>
    request<void>(`/api/admin/roles/${id}`, { method: "DELETE" }),
  /** 角色关联的菜单 ID 列表（super 始终全部） */
  getRoleMenus: (roleId: number) =>
    request<number[]>(`/api/admin/roles/${roleId}/menus`),
  /** 批量设置角色菜单（全量替换；super 不可改 → 403） */
  updateRoleMenus: (roleId: number, menuIds: number[]) =>
    request<number[]>(`/api/admin/roles/${roleId}/menus`, {
      method: "PUT",
      body: JSON.stringify({ menu_ids: menuIds }),
    }),

  // ─── 系统设置 · 菜单管理（M6.2 后端，require_admin）──────────────
  /** 完整菜单树（含 is_visible/is_system，供菜单管理 tab） */
  listMenusTree: () => request<MenuAdminTree[]>("/api/admin/menus/tree"),
  createMenu: (data: MenuInput) =>
    request<MenuAdmin>("/api/admin/menus", { method: "POST", body: JSON.stringify(data) }),
  updateMenu: (id: number, data: MenuUpdateInput) =>
    request<MenuAdmin>(`/api/admin/menus/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteMenu: (id: number) =>
    request<void>(`/api/admin/menus/${id}`, { method: "DELETE" }),
  /** 批量更新菜单排序 */
  updateMenuSort: (items: MenuSortItem[]) =>
    request<number[]>("/api/admin/menus/sort", {
      method: "PUT",
      body: JSON.stringify({ items }),
    }),

  // ─── 系统设置 · 审计日志（M6.3 后端，require_admin）──────────────
  /** 查询审计日志（默认最近 7 天倒序分页） */
  listAuditLogs: (filter?: AuditLogFilter) => {
    const qs = new URLSearchParams();
    if (filter?.user_id != null) qs.set("user_id", String(filter.user_id));
    if (filter?.action) qs.set("action", filter.action);
    if (filter?.target_type) qs.set("target_type", filter.target_type);
    if (filter?.start_date) qs.set("start_date", filter.start_date);
    if (filter?.end_date) qs.set("end_date", filter.end_date);
    if (filter?.limit != null) qs.set("limit", String(filter.limit));
    if (filter?.offset != null) qs.set("offset", String(filter.offset));
    const query = qs.toString();
    return request<AuditLog[]>(`/api/admin/audit-logs${query ? "?" + query : ""}`);
  },
};

/**
 * 以 SSE 方式发起对话,逐事件回调。
 * 后端按 `data: {json}\n\n` 分隔输出事件。
 */
export async function streamChat(
  sessionId: string,
  prompt: string,
  onEvent: (evt: ChatEvent) => void,
  signal?: AbortSignal,
  modelSelection?: ChatModelSelection,
): Promise<void> {
  const body: { prompt: string; model?: string; thinking_level?: string } = { prompt };
  if (modelSelection?.model) body.model = modelSelection.model;
  if (modelSelection?.thinking_level) {
    body.thinking_level = modelSelection.thinking_level;
  }
  const res = await fetch(`/api/sessions/${sessionId}/chat`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  handleUnauthorizedResponse(res);
  if (!res.ok || !res.body) {
    onEvent({ type: "error", message: `HTTP ${res.status}` });
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const blocks = buf.split("\n\n");
    buf = blocks.pop() ?? "";
    for (const block of blocks) {
      const line = block.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(6)) as ChatEvent);
      } catch {
        // 跳过解析失败的行
      }
    }
  }
}

/**
 * 续接运行中会话的 SSE 流,从指定序号之后开始接收事件。
 */
export async function streamRunningSession(
  sessionId: string,
  afterSeq: number,
  onEvent: (evt: RunEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(
    `/api/sessions/${sessionId}/running/stream?after_seq=${encodeURIComponent(afterSeq)}`,
    {
      method: "GET",
      credentials: "same-origin",
      signal,
    },
  );
  handleUnauthorizedResponse(res);
  if (!res.ok || !res.body) {
    onEvent({ seq: afterSeq, event: { type: "error", message: `HTTP ${res.status}` } });
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const blocks = buf.split("\n\n");
    buf = blocks.pop() ?? "";
    for (const block of blocks) {
      const line = block.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(6)) as RunEvent);
      } catch {
        // 跳过解析失败的行
      }
    }
  }
}

/**
 * 读取预览接口的响应体为文本,同时返回 MIME 与大小。
 * 文本/Markdown/JSON 类型预览走这里(图片/视频/PDF 直接给 src 即可)。
 */
export async function fetchPreviewText(
  url: string,
  signal?: AbortSignal,
): Promise<{ text: string; mime: string; size: number; resolvedPath: string | null }> {
  const res = await fetch(url, {
    credentials: "same-origin",
    signal,
    cache: "no-store",
  });
  handleUnauthorizedResponse(res);
  if (!res.ok) {
    // 后端用 HTTPException(detail=...) 返回 JSON,提取 detail 作为错误消息
    let detail = res.statusText;
    try {
      const j = (await res.json()) as { detail?: string };
      if (j.detail) detail = j.detail;
    } catch {
      // 非 JSON 响应,沿用 statusText
    }
    const err = new Error(`HTTP ${res.status}: ${detail}`);
    (err as Error & { status?: number }).status = res.status;
    throw err;
  }
  const mime = res.headers.get("content-type") || "text/plain";
  const encodedResolvedPath = res.headers.get("x-resolved-preview-path");
  let resolvedPath = encodedResolvedPath;
  if (encodedResolvedPath) {
    try {
      resolvedPath = decodeURIComponent(encodedResolvedPath);
    } catch {
      resolvedPath = encodedResolvedPath;
    }
  }
  const text = await res.text();
  // res.headers.get("content-length") 在非自动解码时通常可信
  const size = Number(res.headers.get("content-length") || text.length);
  return { text, mime, size, resolvedPath };
}
