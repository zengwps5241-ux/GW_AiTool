// 对话工作台:会话列表 + 消息流 + 输入区
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type ComponentType,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import type {
  Agent,
  AgentCommand,
  ChatEvent,
  ModelSettings,
  Project,
  Session,
  TeamSpace,
  ThinkingLevelValue,
  UploadedFile,
  UserMe,
  WorkspaceNode,
} from "@/types";
import { api, streamChat, streamRunningSession } from "@/api/client";
import type { BreadcrumbItem } from "@/components/Topbar";
import MarkdownView from "@/components/workspace/MarkdownView";
import FileNameTooltip from "@/components/workspace/FileNameTooltip";
import { useWorkspacePreview } from "@/components/workspace/useWorkspacePreview";
import {
  readStoredModelSelection,
  resolveStoredModelSelection,
  writeStoredModelSelection,
} from "@/lib/chatModelSelection";
import {
  personalWorkspaceApi,
  teamWorkspaceApi,
  type WorkspaceApi,
} from "@/lib/workspaceApi";
import { canMoveWorkspaceNode, isHtmlName, isMarkdownPreview, isTextualMime } from "@/lib/workspace";
import { I } from "@/icons";
import { Avatar, Btn, Kbd, Tag, TypingDots, useToast } from "@/components/ui";
import ToolCall from "@/components/ToolCall";
import { getCommandTrigger, isCommandSelectionKey, replaceCommandTrigger } from "@/lib/commandMenu";
import { uploadedFilesFromBatch, uploadFailureMessage } from "@/lib/uploads";

// ============ 消息模型 ============
// 把 SSE 事件折叠为可渲染的对话轮 (Turn)
type TextPart = { kind: "text"; text: string };
type ToolPart = {
  kind: "tool";
  id: string;
  name: string;
  input: unknown;
  state: "calling" | "success" | "error";
  output?: unknown;
  errorText?: string;
};
type ErrorPart = { kind: "error"; text: string };
/** AI 结构化草稿「待采纳」卡片（M3.1.4） */
type DraftPart = {
  kind: "draft";
  /** (entity_type, draft_id) 唯一键，亦作采纳状态 map 的 key */
  id: string;
  entityType: string;
  entityLabel: string;
  draftId: number;
  projectId: number;
  preview: Record<string, unknown>;
};
type Part = TextPart | ToolPart | ErrorPart | DraftPart;

interface Turn {
  kind: "user" | "assistant";
  parts: Part[];
}

type WorkspaceChoice =
  | { kind: "personal"; id: null; label: string }
  | { kind: "team"; id: number; label: string };

type SessionWorkspaceFilter = WorkspaceChoice | { kind: "all"; id: null; label: string };

const modelControlStyle: CSSProperties = {
  position: "relative",
  display: "inline-flex",
};

const modelMenuStyle: CSSProperties = {
  position: "absolute",
  left: 0,
  bottom: 34,
  zIndex: 30,
  minWidth: 260,
  maxWidth: 360,
  maxHeight: 260,
  overflow: "auto",
  padding: 6,
  background: "var(--surface)",
  border: "1px solid var(--line-2)",
  borderRadius: 12,
  boxShadow: "var(--shadow-lg)",
};

const controlPillStyle: CSSProperties = {
  height: 30,
  display: "inline-flex",
  alignItems: "center",
  gap: 7,
  padding: "0 10px",
  background: "linear-gradient(180deg, var(--surface), var(--bg-2))",
  border: "1px solid var(--line)",
  borderRadius: 999,
  color: "var(--ink-2)",
  cursor: "pointer",
  fontSize: 12,
  fontFamily: "inherit",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.4), var(--shadow-sm)",
  transition: "border-color 140ms, color 140ms, transform 140ms, background 140ms",
};

const sessionMetaTagStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  maxWidth: "100%",
  height: 20,
  padding: "0 6px",
  border: "1px solid var(--line)",
  borderRadius: 6,
  color: "var(--ink-3)",
  background: "var(--surface)",
  fontSize: 11,
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const sessionMetaTextStyle: CSSProperties = {
  minWidth: 0,
  overflow: "hidden",
  textOverflow: "ellipsis",
};


const WORKSPACE_PANEL_MIN_WIDTH = 220;
const WORKSPACE_PANEL_MAX_WIDTH = 520;
const WORKSPACE_PANEL_DEFAULT_WIDTH = 280;

function clampWorkspacePanelWidth(width: number) {
  return Math.min(WORKSPACE_PANEL_MAX_WIDTH, Math.max(WORKSPACE_PANEL_MIN_WIDTH, width));
}

const SESSION_LIST_MIN_WIDTH = 220;
const SESSION_LIST_MAX_WIDTH = 520;
const SESSION_LIST_DEFAULT_WIDTH = 268;

function clampSessionListWidth(width: number) {
  return Math.min(SESSION_LIST_MAX_WIDTH, Math.max(SESSION_LIST_MIN_WIDTH, width));
}

const dropdownMenuStyle: CSSProperties = {
  position: "absolute",
  zIndex: 50,
  top: "calc(100% + 6px)",
  left: 0,
  right: 0,
  background: "var(--surface)",
  border: "1px solid var(--line)",
  borderRadius: 8,
  boxShadow: "var(--shadow-lg)",
  overflow: "hidden",
};


const dropdownEmptyStyle: CSSProperties = {
  padding: "10px",
  color: "var(--ink-3)",
  fontSize: 13,
};

function normalizeUserText(text: string): string {
  const commandName = text.match(/<command-name>\s*([\s\S]*?)\s*<\/command-name>/i)?.[1];
  const commandArgs = text.match(/<command-args>\s*([\s\S]*?)\s*<\/command-args>/i)?.[1];
  // Claude 命令事件会以 XML 片段落到用户消息里,前端展示命令名与用户输入参数。
  if (!commandName) return text;
  return [commandName, commandArgs]
    .map((part) => part?.trim())
    .filter(Boolean)
    .join(" ");
}

function isInputComposing(e: KeyboardEvent<HTMLTextAreaElement>): boolean {
  // 中文/日文等输入法选词时也会触发 Enter,此时不能当成发送快捷键。
  return e.nativeEvent.isComposing || e.key === "Process" || e.keyCode === 229;
}

function eventKey(evt: ChatEvent): string {
  return JSON.stringify(evt);
}

function appendNonDuplicateEvents(
  current: ChatEvent[],
  incoming: ChatEvent[],
): ChatEvent[] {
  if (incoming.length === 0) return current;
  const maxOverlap = Math.min(current.length, incoming.length);
  let overlap = 0;
  // 恢复运行态只裁剪“历史尾部”和“缓存前缀”的重叠，保留后续合法重复事件。
  for (let len = maxOverlap; len > 0; len -= 1) {
    const start = current.length - len;
    const matched = incoming
      .slice(0, len)
      .every((evt, index) => eventKey(current[start + index]) === eventKey(evt));
    if (matched) {
      overlap = len;
      break;
    }
  }
  const remaining = incoming.slice(overlap);
  return remaining.length > 0 ? [...current, ...remaining] : current;
}

// 为历史消息中缺失 tool_result 的 tool_use 补充合成结果，
// 避免前端永久显示“调用中…”。
function ensureHistoricalToolResults(events: ChatEvent[]): ChatEvent[] {
  const hasResult = new Set<string>();
  for (const evt of events) {
    if (evt.type === "tool_result") {
      hasResult.add(evt.tool_use_id);
    }
  }

  const extra: ChatEvent[] = [];
  for (const evt of events) {
    if (evt.type === "tool_use" && !hasResult.has(evt.id)) {
      extra.push({ type: "tool_result", tool_use_id: evt.id, content: "", is_error: false });
    }
  }

  return extra.length > 0 ? [...events, ...extra] : events;
}

// 按事件序列折叠成 Turn[]
function foldEvents(events: ChatEvent[]): Turn[] {
  const out: Turn[] = [];
  // 保证 turns[turns.length-1] 是 assistant turn
  const ensureAssistant = (): Turn => {
    const last = out[out.length - 1];
    if (last && last.kind === "assistant") return last;
    const turn: Turn = { kind: "assistant", parts: [] };
    out.push(turn);
    return turn;
  };

  for (const evt of events) {
    if (evt.type === "user_text") {
      out.push({ kind: "user", parts: [{ kind: "text", text: normalizeUserText(evt.text) }] });
    } else if (evt.type === "assistant_text") {
      const t = ensureAssistant();
      const last = t.parts[t.parts.length - 1];
      if (last && last.kind === "text") {
        last.text += evt.text;
      } else {
        t.parts.push({ kind: "text", text: evt.text });
      }
    } else if (evt.type === "tool_use") {
      const t = ensureAssistant();
      t.parts.push({
        kind: "tool",
        id: evt.id,
        name: evt.name,
        input: evt.input,
        state: "calling",
      });
    } else if (evt.type === "tool_result") {
      const t = ensureAssistant();
      // 找到对应的 tool 块
      const tool = [...t.parts]
        .reverse()
        .find(
          (p): p is ToolPart =>
            p.kind === "tool" && p.id === evt.tool_use_id,
        );
      if (tool) {
        tool.state = evt.is_error ? "error" : "success";
        if (evt.is_error) {
          tool.errorText =
            typeof evt.content === "string"
              ? evt.content
              : JSON.stringify(evt.content);
          tool.output = undefined;
        } else {
          tool.output = evt.content;
          tool.errorText = undefined;
        }
      }
    } else if (evt.type === "draft_pending") {
      // AI 调用 save_xxx_draft 落库后推送的「待采纳」卡片（M3.1.3/M3.1.4）
      const t = ensureAssistant();
      t.parts.push({
        kind: "draft",
        id: `${evt.entity_type}:${evt.draft_id}`,
        entityType: evt.entity_type,
        entityLabel: evt.entity_label,
        draftId: evt.draft_id,
        projectId: evt.project_id,
        preview: evt.preview,
      });
    } else if (evt.type === "error") {
      const t = ensureAssistant();
      t.parts.push({ kind: "error", text: evt.message });
    }
    // result / assistant_thinking 暂不影响显示
  }
  return out;
}

// ============ 时间格式化 ============
function formatTime(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  if (sameDay) {
    return `${String(d.getHours()).padStart(2, "0")}:${String(
      d.getMinutes(),
    ).padStart(2, "0")}`;
  }
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

// ============ 文件大小格式化 ============
function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

const WORKSPACE_DRAG_TYPE = "application/x-workspace-node";
const WORKSPACE_REF_DRAG_TYPE = "application/x-workspace-reference";

function readDraggedWorkspaceNode(dataTransfer: DataTransfer): WorkspaceNode | null {
  const raw = dataTransfer.getData(WORKSPACE_DRAG_TYPE);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as WorkspaceNode;
  } catch {
    return null;
  }
}

// ============ 把附件拼接到用户消息中,让 agent 知道文件位置 ============
// 智能体的 cwd 即用户工作区,因此使用相对路径即可。
function composePromptWithAttachments(
  text: string,
  attached: UploadedFile[],
): string {
  const body = text.trim();
  if (attached.length === 0) return body;
  const list = attached
    .map((f) => `- ${f.name}: ${f.agent_path || f.path}`)
    .join("\n");
  const header = "[已上传附件文件,相对于当前工作目录]";
  return body ? `${body}\n\n${header}\n${list}` : `${header}\n${list}`;
}

// ============ 触发浏览器原生下载 ============
// 用临时 <a download> 让浏览器接管,避免把响应读到 JS 内存里。
function triggerDownload(url: string) {
  const a = document.createElement("a");
  a.href = url;
  a.rel = "noopener";
  // download 属性为 hint:实际文件名由后端 Content-Disposition 决定
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// ============ 主组件 ============
interface Props {
  mode: "all" | "personal" | "team";
  teamSpaceId?: number;
  teamSpaceName?: string;
  initialTeamSpaceFilterVersion?: number;
  initialMode?: "empty" | "chat";
  onModeChange?: (m: "empty" | "chat") => void;
  onOpenWorkspaceDetail?: () => void;
  onOpenTeamSpaces?: () => void;
  onOpenTeamDetail?: (space: { id: number; name: string }) => void;
  onBreadcrumbChange?: (items: BreadcrumbItem[]) => void;
  /** Topbar 选中的项目（M3.4.1）：新建会话时绑定到该项目，加载项目 Agent + 工作流 Skill */
  selectedProject?: Project | null;
  me: UserMe;
}

// 筛选条件芯片
function FilterChip({
  icon,
  label,
  onRemove,
}: {
  icon: ReactNode;
  label: string;
  onRemove: () => void;
}) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "3px 3px 3px 8px",
        background: "var(--bg-2)",
        border: "1px solid var(--line-2)",
        borderRadius: 999,
        fontSize: 11.5,
        fontWeight: 500,
        color: "var(--ink-2)",
        transition: "background 140ms, border-color 140ms",
        animation: "filter-chip-enter 180ms cubic-bezier(0.16, 1, 0.3, 1)",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "var(--bg-3)";
        e.currentTarget.style.borderColor = "var(--line)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "var(--bg-2)";
        e.currentTarget.style.borderColor = "var(--line-2)";
      }}
    >
      {icon}
      <span style={{ maxWidth: 100, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {label}
      </span>
      <button
        type="button"
        onClick={onRemove}
        style={{
          background: "transparent",
          border: "none",
          color: "var(--ink-4)",
          cursor: "pointer",
          padding: 2,
          display: "flex",
          alignItems: "center",
          borderRadius: 999,
          transition: "color 120ms, background 120ms",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = "var(--danger)";
          e.currentTarget.style.background = "var(--danger-soft)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = "var(--ink-4)";
          e.currentTarget.style.background = "transparent";
        }}
      >
        <I.X size={11} />
      </button>
    </span>
  );
}

// ============ 工作流快捷 chip（M3.4.1）============
// 项目级会话可用的 5 个工作流快捷入口：点击向会话发送 `/${command} ${hint}` 触发对应 Skill。
// command 严格对齐 app/skills_seed/<name> 的 Skill 名（项目 Agent 绑定的 7 个 Skill 中 5 个产出型）。
type WfChipIcon = ComponentType<{ size?: number; style?: CSSProperties }>;
interface WfChipDef {
  key: string;
  label: string;
  Icon: WfChipIcon;
  /** Skill 名（即斜杠命令）；点击后发送 `/${command} ${hint}` */
  command: string;
  /** 附在命令后的简短意图说明，帮助模型确定启动该 Skill */
  hint: string;
}
const WF_CHIPS: WfChipDef[] = [
  { key: "hypothesis-map", label: "生成假设地图", Icon: I.Map, command: "consultant-hypothesis-map", hint: "请基于当前项目资料，开始生成分层业务假设地图（L1→L4 分步）。" },
  { key: "visit-plan", label: "生成拜访前方案", Icon: I.ClipboardList, command: "consultant-visit-plan", hint: "请为本项目下一次关键拜访生成前置方案。" },
  { key: "interview", label: "整理拜访纪要", Icon: I.MessagesSquare, command: "consultant-interview", hint: "我将提供拜访纪要素材，请结构化整理并抽取四维度证据。" },
  { key: "verify", label: "验证假设", Icon: I.ClipboardCheck, command: "consultant-verify", hint: "请基于已有证据验证假设地图并更新现状节点。" },
  { key: "stakeholder", label: "营销地图", Icon: I.Users, command: "consultant-stakeholder", hint: "请为本项目生成营销地图角色卡。" },
];

export default function ChatWorkspace({
  mode,
  teamSpaceId,
  teamSpaceName,
  initialTeamSpaceFilterVersion,
  initialMode = "empty",
  onModeChange,
  onOpenWorkspaceDetail,
  onOpenTeamSpaces,
  onOpenTeamDetail,
  onBreadcrumbChange,
  selectedProject,
  me,
}: Props) {
  const { showToast } = useToast();
  const [localMode, setLocalMode] = useState<"empty" | "chat">(initialMode);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [teamSpaces, setTeamSpaces] = useState<TeamSpace[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [pickedAgentId, setPickedAgentId] = useState<number | null>(null);
  const [draftWorkspace, setDraftWorkspace] = useState<WorkspaceChoice>({
    kind: "personal",
    id: null,
    label: "个人空间",
  });
  const [shareDraftSession, setShareDraftSession] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [agentFilterId, setAgentFilterId] = useState<number | null>(null);
  const [workspaceFilter, setWorkspaceFilter] = useState<SessionWorkspaceFilter>({
    kind: "all",
    id: null,
    label: "全部工作空间",
  });
  const [sessionOffset, setSessionOffset] = useState(0);
  const [hasMoreSessions, setHasMoreSessions] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [sessionListWidth, setSessionListWidth] = useState(SESSION_LIST_DEFAULT_WIDTH);
  const [resizingSessionList, setResizingSessionList] = useState(false);
  const sessionListRef = useRef<HTMLDivElement | null>(null);
  const [events, setEvents] = useState<ChatEvent[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [commands, setCommands] = useState<AgentCommand[]>([]);
  const [modelSettings, setModelSettings] = useState<ModelSettings | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [thinkingLevel, setThinkingLevel] = useState<ThinkingLevelValue>("low");
  const [searchKw, setSearchKw] = useState("");
  // 待发送的附件:已通过 /api/uploads 上传到用户工作区,等待随消息一起发出
  const [attached, setAttached] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  // 当前空间文件树:进入会话时加载,流结束后自动刷新
  const [workspace, setWorkspace] = useState<WorkspaceNode[]>([]);
  const [wsLoading, setWsLoading] = useState(false);
  const [wsErr, setWsErr] = useState<string | null>(null);
  const [workspaceCollapsed, setWorkspaceCollapsed] = useState(false);
  const [currentTeamSpace, setCurrentTeamSpace] = useState<TeamSpace | null>(null);
  // 预览模态:同一时刻最多预览一个文件;path=null 即模态关闭
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [previewName, setPreviewName] = useState<string>("");
  // 编辑会话标题状态
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState<string>("");
  const abortRef = useRef<AbortController | null>(null);
  // 用于在流式回调中判断当前是否仍停留在发起聊天的会话,防止消息"窜"到其它会话
  const currentIdRef = useRef<string | null>(null);
  const appliedInitialTeamFilterRef = useRef<number | null>(null);
  const uploadInFlightRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const currentSession = sessions.find((s) => s.id === currentId);
  const activeWorkspaceKind: WorkspaceChoice["kind"] =
    currentSession?.workspace_kind === "team" || (mode === "team" && teamSpaceId)
      ? "team"
      : currentSession?.workspace_kind === "personal"
      ? "personal"
      : draftWorkspace.kind;
  const activeTeamSpaceId =
    currentSession?.workspace_kind === "team"
      ? currentSession.team_space_id
      : mode === "team"
      ? teamSpaceId ?? null
      : draftWorkspace.kind === "team"
      ? draftWorkspace.id
      : null;
  const activeWorkspaceLabel =
    currentSession?.workspace_kind === "team"
      ? currentSession.team_space_name || teamSpaceName || "团队空间"
      : mode === "team"
      ? teamSpaceName || "团队空间"
      : activeWorkspaceKind === "team"
      ? draftWorkspace.label || teamSpaceName || "团队空间"
      : "个人空间";
  const workspaceApi = useMemo<WorkspaceApi>(() => {
    if (activeWorkspaceKind === "team" && activeTeamSpaceId) {
      return teamWorkspaceApi(activeTeamSpaceId);
    }
    return personalWorkspaceApi();
  }, [activeTeamSpaceId, activeWorkspaceKind]);
  const workspaceTitle = activeWorkspaceLabel;
  const workspaceReadonly = activeWorkspaceKind === "team" && currentTeamSpace?.can_write === false;
  const workspaceReadonlyReason = currentTeamSpace?.readonly_reason || "当前空间只读，不能编辑文件";
  const sessionParams = useMemo(() => {
    const base = {
      limit: 10,
      agent_id: agentFilterId,
      mine_only: mode === "personal" || workspaceFilter.kind === "personal",
    };
    if (mode === "team" && teamSpaceId) {
      return {
        ...base,
        workspace_kind: "team" as const,
        team_space_id: teamSpaceId,
        mine_only: false,
      };
    }
    if (mode === "personal") {
      return { ...base, workspace_kind: "personal" as const };
    }
    if (workspaceFilter.kind === "team") {
      return {
        ...base,
        workspace_kind: "team" as const,
        team_space_id: workspaceFilter.id,
      };
    }
    if (workspaceFilter.kind === "personal") {
      return { ...base, workspace_kind: "personal" as const };
    }
    return { ...base, workspace_kind: "all" as const };
  }, [agentFilterId, mode, teamSpaceId, workspaceFilter.id, workspaceFilter.kind]);
  const canLoadSessions = mode !== "team" || Boolean(teamSpaceId);

  useEffect(() => {
    if (!onBreadcrumbChange) return;
    if (currentSession?.workspace_kind === "personal") {
      onBreadcrumbChange(["对话工作台", "个人空间", "会话"]);
      return;
    }
    if (currentSession?.workspace_kind === "team" && currentSession.team_space_id) {
      const teamName = currentSession.team_space_name || teamSpaceName || "团队空间";
      onBreadcrumbChange([
        "对话工作台",
        {
          label: "团队空间",
          onClick: onOpenTeamSpaces,
        },
        {
          label: teamName,
          onClick: onOpenTeamDetail
            ? () => onOpenTeamDetail({ id: currentSession.team_space_id as number, name: teamName })
            : undefined,
        },
        "会话",
      ]);
      return;
    }
    if (mode === "team") {
      onBreadcrumbChange(["对话工作台", "团队空间", teamSpaceName || "团队空间"]);
      return;
    }
    if (workspaceFilter.kind === "personal") {
      onBreadcrumbChange(["对话工作台", "个人空间"]);
      return;
    }
    if (workspaceFilter.kind === "team") {
      onBreadcrumbChange([
        "对话工作台",
        {
          label: "团队空间",
          onClick: onOpenTeamSpaces,
        },
        {
          label: workspaceFilter.label,
          onClick:
            onOpenTeamDetail && workspaceFilter.id !== null
              ? () => onOpenTeamDetail({ id: workspaceFilter.id, name: workspaceFilter.label })
              : undefined,
        },
      ]);
      return;
    }
    onBreadcrumbChange(["对话工作台"]);
  }, [
    currentSession?.team_space_id,
    currentSession?.team_space_name,
    currentSession?.workspace_kind,
    mode,
    onBreadcrumbChange,
    onOpenTeamDetail,
    onOpenTeamSpaces,
    teamSpaceName,
    workspaceFilter,
  ]);

  const setChatMode = useCallback(
    (nextMode: "empty" | "chat") => {
      setLocalMode(nextMode);
      onModeChange?.(nextMode);
    },
    [onModeChange],
  );

  // 保证 ref 始终持有最新的 currentId
  currentIdRef.current = currentId;

  useEffect(() => {
    setLocalMode(initialMode);
  }, [initialMode]);

  useEffect(() => {
    if (
      mode !== "all" ||
      !teamSpaceId ||
      initialTeamSpaceFilterVersion === undefined ||
      appliedInitialTeamFilterRef.current === initialTeamSpaceFilterVersion
    ) {
      return;
    }
    const initialTeamWorkspace: WorkspaceChoice = {
      kind: "team",
      id: teamSpaceId,
      label: teamSpaceName || "团队空间",
    };
    appliedInitialTeamFilterRef.current = initialTeamSpaceFilterVersion;
    setWorkspaceFilter(initialTeamWorkspace);
    setDraftWorkspace(initialTeamWorkspace);
  }, [initialTeamSpaceFilterVersion, mode, teamSpaceId, teamSpaceName]);

  useEffect(() => {
    if (activeWorkspaceKind !== "team" || !activeTeamSpaceId) {
      setCurrentTeamSpace(null);
      return;
    }
    let cancelled = false;
    api.teamSpace(activeTeamSpaceId)
      .then((space) => {
        if (!cancelled) setCurrentTeamSpace(space);
      })
      .catch(() => {
        if (!cancelled) setCurrentTeamSpace(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTeamSpaceId, activeWorkspaceKind]);

  const loadSessions = useCallback(
    async (offset = 0, append = false) => {
      if (!canLoadSessions) {
        setSessions([]);
        setHasMoreSessions(false);
        return;
      }
      setSessionLoading(true);
      try {
        const items = await api.sessions({ ...sessionParams, offset });
        setSessions((prev) => (append ? [...prev, ...items] : items));
        setSessionOffset(offset);
        setHasMoreSessions(items.length === 10);
      } catch {
        if (!append) setSessions([]);
        setHasMoreSessions(false);
      } finally {
        setSessionLoading(false);
      }
    },
    [canLoadSessions, sessionParams],
  );

  // 初始加载:并发拉取智能体、团队空间与会话列表
  useEffect(() => {
    if (!canLoadSessions) {
      setSessions([]);
      return;
    }
    Promise.all([api.agents(), api.teamSpaces(), api.sessions({ ...sessionParams, offset: 0 })])
      .then(([as, spaces, ss]) => {
        setAgents(as);
        setTeamSpaces(spaces);
        setSessions(ss);
        setSessionOffset(0);
        setHasMoreSessions(ss.length === 10);
        const def = as.find((a) => a.is_default) || as[0];
        if (def) setPickedAgentId(def.id);
        if (mode === "team" && teamSpaceId) {
          const current = spaces.find((space) => space.id === teamSpaceId);
          setDraftWorkspace({
            kind: "team",
            id: teamSpaceId,
            label: current?.name || teamSpaceName || "团队空间",
          });
          setWorkspaceFilter({
            kind: "team",
            id: teamSpaceId,
            label: current?.name || teamSpaceName || "团队空间",
          });
        }
      })
      .catch(() => {
        // 忽略加载失败,UI 会展示空状态
      });
  }, [canLoadSessions, mode, sessionParams, teamSpaceId, teamSpaceName]);

  // 模型设置独立加载；失败时保持空选择，不影响基础对话能力。
  useEffect(() => {
    let cancelled = false;
    api.modelSettings()
      .then((settings) => {
        if (cancelled) return;
        const restored = resolveStoredModelSelection(
          settings,
          readStoredModelSelection(),
        );
        setModelSettings(settings);
        setSelectedModel(restored.model);
        setThinkingLevel(restored.thinkingLevel);
      })
      .catch(() => {
        if (!cancelled) {
          setModelSettings(null);
          setSelectedModel(null);
          setThinkingLevel("low");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 用户切换后写入本地缓存，刷新页面时继续使用上次选择。
  useEffect(() => {
    if (!modelSettings) return;
    writeStoredModelSelection(selectedModel, thinkingLevel);
  }, [modelSettings, selectedModel, thinkingLevel]);

  // 自动滚动到底部
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [events, streaming]);

  const visibleSessions = useMemo(() => {
    const keyword = searchKw.trim().toLowerCase();
    if (!keyword) return sessions;
    return sessions.filter((s) =>
      [s.title, s.agent_name || "", s.team_space_name || ""]
        .join(" ")
        .toLowerCase()
        .includes(keyword),
    );
  }, [sessions, searchKw]);

  const turns = useMemo(() => foldEvents(events), [events]);

  const workspaceOptions = useMemo<WorkspaceChoice[]>(
    () => [
      { kind: "personal", id: null, label: "个人空间" },
      ...teamSpaces.map((space) => ({
        kind: "team" as const,
        id: space.id,
        label: space.name,
      })),
    ],
    [teamSpaces],
  );
  const workspaceFilterOptions = useMemo<SessionWorkspaceFilter[]>(
    () =>
      mode === "team" && teamSpaceId
        ? [{ kind: "team", id: teamSpaceId, label: teamSpaceName || "团队空间" }]
        : [
            { kind: "all", id: null, label: "全部工作空间" },
            ...workspaceOptions,
          ],
    [mode, teamSpaceId, teamSpaceName, workspaceOptions],
  );

  // 用户主动离开当前流会话时立即清理页面态，不等待旧流 finally。
  const clearActiveStream = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
    abortRef.current = null;
  }, []);

  // 删除会话
  const deleteSession = useCallback(
    async (id: string) => {
      if (!confirm("删除这条会话?")) return;
      try {
        await api.deleteSession(id);
      } catch {
        return;
      }
      setSessions((list) => list.filter((s) => s.id !== id));
      if (currentId === id) {
        clearActiveStream();
        setCurrentId(null);
        currentIdRef.current = null;
        setEvents([]);
        setChatMode("empty");
      }
    },
    [clearActiveStream, currentId, setChatMode],
  );

  // 开始编辑会话标题
  const startEdit = useCallback((s: Session) => {
    setEditingId(s.id);
    setEditingTitle(s.title);
  }, []);

  // 保存会话标题
  const saveTitle = useCallback(
    async (id: string, title: string) => {
      const trimmed = title.trim();
      if (!trimmed) {
        setEditingId(null);
        return;
      }
      try {
        await api.updateSessionTitle(id, trimmed);
        setSessions((list) =>
          list.map((s) => (s.id === id ? { ...s, title: trimmed } : s)),
        );
      } catch {
        // 保存失败,保持原样
      }
      setEditingId(null);
    },
    [],
  );

  // 取消编辑
  const cancelEdit = useCallback(() => {
    setEditingId(null);
    setEditingTitle("");
  }, []);

  // 新建对话(回到空状态)
  const newSession = useCallback(() => {
    clearActiveStream();
    setCurrentId(null);
    currentIdRef.current = null;
    setEvents([]);
    setInput("");
    setAttached([]);
    setUploadErr(null);
    setChatMode("empty");
  }, [clearActiveStream, setChatMode]);

  // 加载当前空间文件树:进入会话、上传后、流结束后均会调用。
  const loadWorkspace = useCallback(async () => {
    setWsLoading(true);
    setWsErr(null);
    try {
      const tree = await workspaceApi.tree();
      setWorkspace(tree);
    } catch (e) {
      setWsErr((e as Error).message || `加载${workspaceTitle}失败`);
    } finally {
      setWsLoading(false);
    }
  }, [workspaceApi, workspaceTitle]);

  // 统一收尾:仅允许当前会话的流清理 streaming/abortRef,避免旧流结束影响新会话。
  const finishStreaming = useCallback(async (sid?: string) => {
    if (sid && currentIdRef.current !== sid) return;
    setStreaming(false);
    abortRef.current = null;
    try {
      const ss = canLoadSessions ? await api.sessions({ ...sessionParams, offset: 0 }) : [];
      setSessions(ss);
      setSessionOffset(0);
      setHasMoreSessions(ss.length === 10);
    } catch {
      // 忽略会话列表刷新失败,避免影响主流程
    }
    await loadWorkspace();
  }, [canLoadSessions, loadWorkspace, sessionParams]);

  // 恢复后端仍在运行的会话流,用于进入历史会话后继续接收事件。
  const restoreRunningSession = useCallback(
    async (sid: string) => {
      let runningState: Awaited<ReturnType<typeof api.sessionRunning>>;
      try {
        runningState = await api.sessionRunning(sid);
      } catch {
        return;
      }
      if (!runningState.running) return;
      if (currentIdRef.current !== sid) return;

      const cachedEvents = runningState.events.map((item) => item.event);
      if (cachedEvents.length > 0) {
        setEvents((es) => appendNonDuplicateEvents(es, cachedEvents));
      }
      setStreaming(true);

      const ac = new AbortController();
      abortRef.current = ac;
      try {
        await streamRunningSession(
          sid,
          runningState.latest_seq,
          (item) => {
            // 会话已切换时丢弃恢复流事件,防止写入当前页面。
            if (currentIdRef.current !== sid) return;
            setEvents((es) => [...es, item.event]);
          },
          ac.signal,
        );
      } catch {
        // 中止或网络异常都交给 finally 做收尾判断
      } finally {
        await finishStreaming(sid);
      }
    },
    [finishStreaming],
  );

  // 选中会话
  const selectSession = useCallback(
    async (id: string) => {
      if (id === currentId) return;
      clearActiveStream();
      setCurrentId(id);
      currentIdRef.current = id;
      setEvents([]);
      setChatMode("chat");
      try {
        const msgs = await api.sessionMessages(id);
        if (currentIdRef.current !== id) return;
        setEvents(ensureHistoricalToolResults(msgs));
        restoreRunningSession(id);
      } catch {
        if (currentIdRef.current !== id) return;
        setEvents([{ type: "error", message: "加载历史消息失败" }]);
      }
    },
    [clearActiveStream, currentId, restoreRunningSession, setChatMode],
  );

  // 打开/关闭预览模态
  const openPreview = useCallback((node: WorkspaceNode) => {
    setPreviewPath(node.path);
    setPreviewName(node.name);
  }, []);
  const closePreview = useCallback(() => {
    setPreviewPath(null);
    setPreviewName("");
  }, []);

  useEffect(() => {
    clearActiveStream();
    setCurrentId(null);
    currentIdRef.current = null;
    setEvents([]);
    setInput("");
    setAttached([]);
    setUploadErr(null);
    setWorkspace([]);
    closePreview();
    setChatMode("empty");
  }, [clearActiveStream, closePreview, mode, setChatMode, teamSpaceId]);

  // 始终加载当前空间文件树;切换会话或空间时刷新
  useEffect(() => {
    loadWorkspace();
    // 切换或离开会话时关闭预览模态,避免显示已不属于当前上下文的内容
    closePreview();
  }, [currentId, loadWorkspace, closePreview]);

  // 上传文件:个人空间沿用批量上传接口;团队空间使用空间内上传任务。
  const uploadFiles = useCallback(
    async (files: FileList | File[]) => {
      if (uploadInFlightRef.current) return;
      if (workspaceReadonly) {
        showToast(workspaceReadonlyReason, "info");
        return;
      }
      const list = Array.from(files);
      if (list.length === 0) return;
      uploadInFlightRef.current = true;
      setUploading(true);
      setUploadErr(null);
      try {
        if (activeWorkspaceKind === "team") {
          const createdTasks = await workspaceApi.createUploadTasks(
            "uploads",
            list.map((file) => ({
              filename: file.name,
              relative_path: file.name,
              size: file.size,
            })),
          );
          const uploaded: UploadedFile[] = [];
          for (let index = 0; index < createdTasks.length; index += 1) {
            const task = createdTasks[index];
            const file = list[index];
            if (!task || !file) continue;
            const finished = await workspaceApi.uploadTaskFile(task.id, file);
            if (finished.status === "succeeded" && finished.saved_path) {
              uploaded.push({
                name: finished.filename,
                path: finished.saved_path,
                size: finished.size,
                preview_path: finished.saved_path,
                agent_path: finished.saved_path,
                converted: false,
              });
            }
          }
          setAttached((prev) => [...prev, ...uploaded]);
        } else {
          const batch = await api.uploadFilesToWorkspace(list, {
            targetDir: "uploads",
            relativePaths: list.map((f) => f.name),
          });
          const failedMessage = uploadFailureMessage(batch);
          if (failedMessage) {
            setUploadErr(failedMessage);
            showToast(failedMessage, "error");
          }
          const uploaded = uploadedFilesFromBatch(batch);
          setAttached((prev) => [...prev, ...uploaded]);
        }
        // 上传成功后立刻刷新空间树,用户能立即看到新文件
        loadWorkspace();
      } catch (e) {
        const message = (e as Error).message || "上传失败,请重试";
        setUploadErr(message);
        showToast(message, "error");
      } finally {
        uploadInFlightRef.current = false;
        setUploading(false);
      }
    },
    [activeWorkspaceKind, loadWorkspace, showToast, workspaceApi, workspaceReadonly, workspaceReadonlyReason],
  );

  // 移除某个待发送附件(只从前端列表中移除,后端文件保留在工作区不动)
  const removeAttachment = useCallback((path: string) => {
    setAttached((prev) => prev.filter((f) => f.path !== path));
  }, []);

  // 把个人空间中的文件/目录"引用"到输入框附件列表;与已上传文件复用同一展示
  // 目录也允许引用,size 缺失时填 0;按 path 去重,避免重复添加
  // 注:已转换为 markdown 的源文件,后端会下发 ``agent_path`` 指向 .markdown 内的 md,
  // 这里把它直接透传给智能体,避免智能体读到不可解析的 PDF/Word 原文件。
  const referenceWorkspaceNode = useCallback((node: WorkspaceNode) => {
    setAttached((prev) => {
      if (prev.some((f) => f.path === node.path)) return prev;
      const agentPath = node.agent_path ?? node.path;
      return [
        ...prev,
        {
          name: node.name,
          path: node.path,
          size: node.size ?? 0,
          preview_path: node.path,
          agent_path: agentPath,
          converted: Boolean(node.agent_path),
        },
      ];
    });
  }, []);

  // 移动文件或目录到目标目录
  const moveWorkspaceNode = useCallback(
    async (node: WorkspaceNode, targetDir: string) => {
      if (!canMoveWorkspaceNode(node, targetDir)) return;
      if (workspaceReadonly) {
        showToast(workspaceReadonlyReason, "info");
        return;
      }
      try {
        await workspaceApi.moveItem(node.path, targetDir);
        await loadWorkspace();
      } catch (e) {
        showToast((e as Error).message || "移动失败", "error");
      }
    },
    [loadWorkspace, showToast, workspaceApi, workspaceReadonly, workspaceReadonlyReason],
  );

  // 发送消息(若无 currentId 则先创建会话)
  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      // 允许"仅附件"发送:只要有附件或文本之一即可
      if (!trimmed && attached.length === 0) return;
      if (streaming) return;

      let sid = currentId;
      if (!sid) {
        const createWorkspaceKind = mode === "team" ? "team" : draftWorkspace.kind;
        const createTeamSpaceId =
          mode === "team" ? teamSpaceId ?? null : draftWorkspace.kind === "team" ? draftWorkspace.id : null;
        if (createWorkspaceKind === "team" && !createTeamSpaceId) {
          setEvents((es) => [...es, { type: "error", message: "团队空间未选中" }]);
          return;
        }
        try {
          const created = await api.createSession({
            // 项目会话（M3.4.1）：Topbar 已选项目时绑定 project_id，后端自动加载项目 Agent
            // （含 7 个工作流 Skill + 3 Plugin），不传 agent_id；普通会话沿用用户挑选的 Agent。
            ...(selectedProject
              ? { project_id: selectedProject.id }
              : { agent_id: pickedAgentId }),
            workspace_kind: createWorkspaceKind,
            team_space_id: createTeamSpaceId,
            is_shared: createWorkspaceKind === "team" ? shareDraftSession : false,
          });
          setSessions((list) => [created, ...list]);
          sid = created.id;
          setCurrentId(sid);
          currentIdRef.current = sid;
          setChatMode("chat");
        } catch {
          setEvents((es) => [...es, { type: "error", message: "创建会话失败" }]);
          return;
        }
      }

      // 把附件路径拼到 prompt 末尾,智能体可直接据此读取文件
      const finalPrompt = composePromptWithAttachments(trimmed, attached);

      // 立即追加用户消息事件,优化反馈感
      setEvents((es) => [...es, { type: "user_text", text: finalPrompt }]);
      setInput("");
      setAttached([]);
      setUploadErr(null);
      setStreaming(true);

      const ac = new AbortController();
      abortRef.current = ac;
      try {
        await streamChat(
          sid,
          finalPrompt,
          (evt) => {
            // 如果用户已经切到其它会话,丢弃该事件,防止消息"窜"会话
            if (currentIdRef.current !== sid) return;
            setEvents((es) => [...es, evt]);
          },
          ac.signal,
          {
            model: selectedModel,
            thinking_level: thinkingLevel,
          },
        );
      } catch {
        // 中止或网络异常都按结束流程
      } finally {
        await finishStreaming(sid);
      }
    },
    [
      streaming,
      currentId,
      pickedAgentId,
      mode,
      teamSpaceId,
      draftWorkspace,
      shareDraftSession,
      setChatMode,
      attached,
      selectedModel,
      thinkingLevel,
      finishStreaming,
      selectedProject,
    ],
  );

  // 停止当前流式输出
  const stopStream = useCallback(async () => {
    if (!currentId) return;
    try {
      await api.stopSession(currentId);
    } catch {
      // 忽略
    }
    abortRef.current?.abort();
  }, [currentId]);

  // 输入框回车发送
  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (isInputComposing(e)) return;
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage(input);
      }
    },
    [input, sendMessage],
  );

  // ============ 渲染 ============
  const isEmpty = localMode === "empty" || !currentId;
  // 当前对话的项目上下文（M3.4.1）：
  //  - 空状态（尚未建会话）：以 Topbar 选中的项目作为「待绑定」项目，新建会话将关联它；
  //  - 已进入会话：仅当该会话本身是项目会话（project_id）才视为项目上下文（旧的非项目会话不变）。
  const activeProjectId = isEmpty
    ? selectedProject?.id ?? null
    : currentSession?.project_id ?? null;
  const activeProjectName = isEmpty
    ? selectedProject?.name ?? null
    : currentSession?.project_name ?? null;
  const hasProjectContext = activeProjectId != null;
  const commandAgentId = currentSession?.agent_id ?? (isEmpty ? pickedAgentId : null);

  useEffect(() => {
    let cancelled = false;
    if (!commandAgentId) {
      setCommands([]);
      return;
    }
    api.agentCommands(commandAgentId)
      .then((items) => {
        if (!cancelled) setCommands(items);
      })
      .catch(() => {
        if (!cancelled) setCommands([]);
      });
    return () => {
      cancelled = true;
    };
  }, [commandAgentId]);

  useEffect(() => {
    if (!resizingSessionList) return;
    const onMouseMove = (e: MouseEvent) => {
      const left = sessionListRef.current?.getBoundingClientRect().left ?? 0;
      setSessionListWidth(clampSessionListWidth(e.clientX - left));
    };
    const onMouseUp = () => setResizingSessionList(false);
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [resizingSessionList]);

  return (
    <div style={{ flex: 1, display: "flex", minHeight: 0, background: "var(--bg)" }}>
      {/* 会话列表 */}
      <div
        ref={sessionListRef}
        style={{
          width: sessionListWidth,
          flex: `0 0 ${sessionListWidth}px`,
          background: "var(--bg-2)",
          borderRight: "1px solid var(--line)",
          display: "flex",
          flexDirection: "column",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            padding: 12,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            borderBottom: "1px solid var(--line)",
            position: "relative",
          }}
        >
          <Btn
            variant="primary"
            icon={<I.Plus size={14} />}
            onClick={newSession}
            block
          >
            新建对话
          </Btn>

          {/* 搜索栏 */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              height: 38,
              padding: "0 12px",
              minWidth: 0,
              boxSizing: "border-box",
              background: "var(--surface)",
              border: `1.5px solid ${filterOpen ? "var(--accent-soft)" : "var(--line-2)"}`,
              borderRadius: 10,
              transition: "border-color 180ms, box-shadow 180ms",
              boxShadow: filterOpen ? "0 0 0 3px var(--accent-soft)" : "none",
            }}
          >
            <I.Search size={14} style={{ color: "var(--ink-4)", flexShrink: 0 }} />
            <input
              type="text"
              placeholder="搜索会话"
              value={searchKw}
              onChange={(e) => setSearchKw(e.target.value)}
              style={{
                flex: 1,
                minWidth: 0,
                border: "none",
                outline: "none",
                background: "transparent",
                fontSize: 13,
                color: "var(--ink)",
                fontFamily: "inherit",
                height: "100%",
              }}
            />
            {searchKw && (
              <button
                type="button"
                onClick={() => setSearchKw("")}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--ink-4)",
                  cursor: "pointer",
                  padding: 0,
                  display: "flex",
                  alignItems: "center",
                  flexShrink: 0,
                }}
              >
                <I.X size={14} />
              </button>
            )}
            <div
              style={{
                width: 1,
                height: 18,
                background: "var(--line-2)",
                margin: "0 2px",
                flexShrink: 0,
              }}
            />
            <button
              type="button"
              onClick={() => setFilterOpen((open) => !open)}
              title="筛选"
              style={{
                width: 28,
                height: 26,
                padding: 0,
                border: `1.5px solid ${
                  filterOpen || agentFilterId || workspaceFilter.kind !== "all"
                    ? "var(--accent-soft)"
                    : "transparent"
                }`,
                borderRadius: 7,
                background:
                  filterOpen || agentFilterId || workspaceFilter.kind !== "all"
                    ? "var(--accent-soft)"
                    : "transparent",
                color:
                  filterOpen || agentFilterId || workspaceFilter.kind !== "all"
                    ? "var(--accent-2)"
                    : "var(--ink-4)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 4,
                cursor: "pointer",
                fontSize: 11,
                fontWeight: 600,
                fontFamily: "inherit",
                flex: "0 0 28px",
                transition: "all 160ms ease",
              }}
              onMouseEnter={(e) => {
                if (!filterOpen) {
                  e.currentTarget.style.background = "var(--bg-2)";
                  e.currentTarget.style.color = "var(--ink-2)";
                }
              }}
              onMouseLeave={(e) => {
                if (!filterOpen) {
                  e.currentTarget.style.background = "transparent";
                  e.currentTarget.style.color =
                    agentFilterId || workspaceFilter.kind !== "all"
                      ? "var(--accent-2)"
                      : "var(--ink-4)";
                }
              }}
            >
              <I.Filter size={13} />
              {(agentFilterId || workspaceFilter.kind !== "all") && !filterOpen && (
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: 999,
                    background: "var(--accent)",
                    display: "inline-block",
                  }}
                />
              )}
            </button>
          </div>

          {/* 已选筛选条件芯片 */}
          {(agentFilterId || workspaceFilter.kind !== "all") && !filterOpen && (
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 6,
                animation: "filter-chip-enter 200ms cubic-bezier(0.16, 1, 0.3, 1)",
              }}
            >
              {agentFilterId && (
                <FilterChip
                  icon={
                    <span
                      style={{
                        width: 16,
                        height: 16,
                        borderRadius: 999,
                        background: `${getAgentColor(
                          agents.find((a) => a.id === agentFilterId)?.name || "",
                        )}20`,
                        color: getAgentColor(
                          agents.find((a) => a.id === agentFilterId)?.name || "",
                        ),
                        fontSize: 9,
                        fontWeight: 700,
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      {agents
                        .find((a) => a.id === agentFilterId)
                        ?.name?.[0]
                        ?.toUpperCase() || "?"}
                    </span>
                  }
                  label={agents.find((a) => a.id === agentFilterId)?.name || ""}
                  onRemove={() => {
                    setAgentFilterId(null);
                    setSessionOffset(0);
                  }}
                />
              )}
              {workspaceFilter.kind !== "all" && (
                <FilterChip
                  icon={
                    workspaceFilter.kind === "team" ? (
                      <I.Folders size={12} style={{ color: "var(--info)" }} />
                    ) : (
                      <I.Folder size={12} style={{ color: "var(--success)" }} />
                    )
                  }
                  label={workspaceFilter.label}
                  onRemove={() => {
                    setWorkspaceFilter({ kind: "all", id: null, label: "全部工作空间" });
                    setSessionOffset(0);
                  }}
                />
              )}
            </div>
          )}

          {filterOpen && (
            <SessionFilterPanel
              agents={agents}
              workspaceOptions={workspaceFilterOptions}
              agentId={agentFilterId}
              workspace={workspaceFilter}
              workspaceLocked={mode === "team"}
              onAgentChange={(id) => {
                setAgentFilterId(id);
                setSessionOffset(0);
              }}
              onWorkspaceChange={(workspace) => {
                setWorkspaceFilter(workspace);
                setSessionOffset(0);
              }}
              onClose={() => setFilterOpen(false)}
            />
          )}
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: "8px 8px 16px" }}>
          {visibleSessions.length === 0 && (
            <div
              style={{
                padding: 28,
                color: "var(--ink-4)",
                fontSize: 12.5,
                textAlign: "center",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 8,
              }}
            >
              <I.Search size={24} style={{ opacity: 0.4 }} />
              <div>{searchKw.trim() ? "未找到匹配的会话" : "暂无会话"}</div>
              {searchKw.trim() && (
                <button
                  type="button"
                  onClick={() => setSearchKw("")}
                  style={{
                    color: "var(--accent-2)",
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    fontSize: 12.5,
                    fontFamily: "inherit",
                  }}
                >
                  清除搜索
                </button>
              )}
            </div>
          )}
          {visibleSessions.map((s, index) => {
                const active = s.id === currentId;
                return (
                  <div
                    key={s.id}
                    onClick={() => selectSession(s.id)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "10px 12px",
                      background: active ? "var(--surface)" : "transparent",
                      border: `1px solid ${active ? "var(--line-2)" : "transparent"}`,
                      borderRadius: 10,
                      cursor: "pointer",
                      transition: "background 160ms ease, border-color 160ms ease, transform 160ms ease, box-shadow 160ms ease",
                      marginBottom: 4,
                      position: "relative",
                      boxShadow: active ? "0 1px 3px rgba(31,27,23,0.04)" : "none",
                      animation: `session-card-enter 220ms ${Math.min(index * 30, 300)}ms cubic-bezier(0.16, 1, 0.3, 1) backwards`,
                    }}
                    onMouseEnter={(e) => {
                      if (!active) {
                        e.currentTarget.style.background = "var(--surface)";
                        e.currentTarget.style.borderColor = "var(--line-2)";
                        e.currentTarget.style.transform = "translateY(-1px)";
                        e.currentTarget.style.boxShadow = "0 2px 8px rgba(31,27,23,0.05)";
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!active) {
                        e.currentTarget.style.background = "transparent";
                        e.currentTarget.style.borderColor = "transparent";
                        e.currentTarget.style.transform = "none";
                        e.currentTarget.style.boxShadow = "none";
                      }
                    }}
                  >
                    {/* 激活指示条 */}
                    {active && (
                      <div
                        style={{
                          position: "absolute",
                          left: 0,
                          top: 10,
                          bottom: 10,
                          width: 3,
                          borderRadius: "0 3px 3px 0",
                          background: "var(--accent)",
                        }}
                      />
                    )}
                    <div style={{ flex: 1, minWidth: 0, paddingLeft: active ? 4 : 0, transition: "padding 160ms" }}>
                      {editingId === s.id ? (
                        <input
                          autoFocus
                          value={editingTitle}
                          onChange={(e) => setEditingTitle(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              saveTitle(s.id, editingTitle);
                            } else if (e.key === "Escape") {
                              cancelEdit();
                            }
                          }}
                          onBlur={() => saveTitle(s.id, editingTitle)}
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            fontSize: 13,
                            fontWeight: 500,
                            color: "var(--ink)",
                            background: "var(--bg)",
                            border: "1.5px solid var(--accent-soft)",
                            borderRadius: 6,
                            padding: "3px 8px",
                            width: "100%",
                            outline: "none",
                            boxShadow: "0 0 0 3px var(--accent-soft)",
                          }}
                        />
                      ) : (
                        <div
                          style={{
                            fontSize: 13,
                            fontWeight: 600,
                            color: "var(--ink)",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            lineHeight: 1.4,
                          }}
                        >
                          {s.title}
                        </div>
                      )}
                      <div
                        style={{
                          fontSize: 11,
                          color: "var(--ink-4)",
                          marginTop: 3,
                          fontWeight: 500,
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        <span>{formatTime(s.updated_at)}</span>
                      </div>
                      <div
                        style={{
                          display: "flex",
                          gap: 5,
                          flexWrap: "wrap",
                          marginTop: 8,
                        }}
                      >
                        <span
                          style={{
                            ...sessionMetaTagStyle,
                            borderColor: "var(--line-2)",
                            background: active ? "var(--bg-2)" : "var(--surface)",
                          }}
                        >
                          <I.Brain size={11} />
                          <span style={sessionMetaTextStyle}>{s.agent_name || "未分配智能体"}</span>
                        </span>
                        <span
                          style={{
                            ...sessionMetaTagStyle,
                            borderColor: "var(--line-2)",
                            background: active ? "var(--bg-2)" : "var(--surface)",
                          }}
                        >
                          {s.workspace_kind === "team" ? <I.Folders size={11} /> : <I.Folder size={11} />}
                          <span style={sessionMetaTextStyle}>
                            {s.workspace_kind === "team"
                              ? s.team_space_name || "团队空间"
                              : "个人空间"}
                          </span>
                        </span>
                        {s.project_name && (
                          <span
                            style={{
                              ...sessionMetaTagStyle,
                              borderColor: "var(--accent-soft)",
                              background: "var(--accent-soft)",
                              color: "var(--accent-2)",
                            }}
                          >
                            <I.Briefcase size={11} />
                            <span style={sessionMetaTextStyle}>{s.project_name}</span>
                          </span>
                        )}
                        {s.is_shared && (
                          <span
                            style={{
                              ...sessionMetaTagStyle,
                              borderColor: "var(--info-soft)",
                              background: "var(--info-soft)",
                              color: "var(--info)",
                            }}
                          >
                            <I.Users size={10} /> 共享
                          </span>
                        )}
                      </div>
                    </div>
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: 2,
                        opacity: active ? 0.8 : 0,
                        transition: "opacity 160ms ease",
                      }}
                      className="session-actions"
                    >
                      {editingId !== s.id && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            startEdit(s);
                          }}
                          style={{
                            background: "transparent",
                            border: "none",
                            color: "var(--ink-3)",
                            cursor: "pointer",
                            padding: 4,
                            borderRadius: 5,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            transition: "background 120ms, color 120ms",
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = "var(--bg-2)";
                            e.currentTarget.style.color = "var(--ink)";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = "transparent";
                            e.currentTarget.style.color = "var(--ink-3)";
                          }}
                          title="编辑标题"
                        >
                          <I.Edit size={12} />
                        </button>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteSession(s.id);
                        }}
                        style={{
                          background: "transparent",
                          border: "none",
                          color: "var(--ink-3)",
                          cursor: "pointer",
                          padding: 4,
                          borderRadius: 5,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          transition: "background 120ms, color 120ms",
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = "var(--danger-soft)";
                          e.currentTarget.style.color = "var(--danger)";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = "transparent";
                          e.currentTarget.style.color = "var(--ink-3)";
                        }}
                        title="删除会话"
                      >
                        <I.Trash size={12} />
                      </button>
                    </div>
                  </div>
                );
          })}
          {hasMoreSessions && !searchKw.trim() && (
            <Btn
              variant="secondary"
              size="sm"
              block
              disabled={sessionLoading}
              onClick={() => void loadSessions(sessionOffset + 10, true)}
              style={{ marginTop: 8 }}
            >
              {sessionLoading ? "加载中" : "更多"}
            </Btn>
          )}
        </div>
      </div>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="调整会话列表宽度"
        tabIndex={0}
        title="拖拽调整会话列表宽度"
        onMouseDown={(e) => {
          e.preventDefault();
          setResizingSessionList(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") {
            e.preventDefault();
            setSessionListWidth((width) => clampSessionListWidth(width - 16));
          }
          if (e.key === "ArrowRight") {
            e.preventDefault();
            setSessionListWidth((width) => clampSessionListWidth(width + 16));
          }
        }}
        style={{
          width: 6,
          flex: "0 0 6px",
          cursor: "col-resize",
          background: resizingSessionList ? "var(--accent-soft)" : "transparent",
          borderRight: resizingSessionList ? "1px solid var(--accent)" : "1px solid transparent",
        }}
      />

      {/* 主对话区 */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minWidth: 0,
        }}
      >
        {/* 标题栏 */}
        <div
          style={{
            height: 48,
            padding: "0 16px",
            borderBottom: "1px solid var(--line)",
            display: "flex",
            alignItems: "center",
            gap: 12,
            flexShrink: 0,
          }}
        >
          <div
            style={{
              flex: 1,
              fontSize: 14,
              fontWeight: 500,
              color: "var(--ink)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {isEmpty ? `新建对话 · ${workspaceTitle}` : currentSession?.title || "对话"}
          </div>
          {currentSession?.agent_name && (
            <Tag tone="accent">
              <I.Users size={11} />
              {currentSession.agent_name}
            </Tag>
          )}
          {currentSession?.project_name && (
            <Tag tone="neutral">
              <I.Briefcase size={11} />
              {currentSession.project_name}
            </Tag>
          )}
        </div>

        {/* 消息流 */}
        <div ref={scrollRef} style={{ flex: 1, overflow: "auto" }}>
          {isEmpty ? (
            <EmptyState
              agents={agents}
              pickedAgentId={pickedAgentId}
              onPickAgent={setPickedAgentId}
              workspaceOptions={mode === "team" ? workspaceFilterOptions.filter((item): item is WorkspaceChoice => item.kind !== "all") : workspaceOptions}
              workspace={draftWorkspace}
              onPickWorkspace={(workspace) => {
                setDraftWorkspace(workspace);
                setShareDraftSession(false);
              }}
              shareSession={shareDraftSession}
              onShareSessionChange={setShareDraftSession}
              projectName={hasProjectContext ? activeProjectName : null}
            />
          ) : (
            <div
              style={{
                maxWidth: 820,
                margin: "0 auto",
                padding: "24px 24px 12px",
                display: "flex",
                flexDirection: "column",
                gap: 22,
              }}
            >
              {turns.map((turn, i) => (
                <TurnView key={i} turn={turn} username={me.display_name ?? me.username} />
              ))}
              {streaming && (
                <div
                  style={{
                    display: "flex",
                    gap: 12,
                    alignItems: "center",
                  }}
                >
                  <span
                    style={{
                      width: 30,
                      height: 30,
                      borderRadius: 999,
                      background: "var(--surface)",
                      border: "1px solid var(--line)",
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "var(--accent)",
                      animation: "breathe 1.6s ease-in-out infinite",
                    }}
                  >
                    <I.Logo size={16} />
                  </span>
                  <TypingDots />
                </div>
              )}
            </div>
          )}
        </div>

        {/* 输入区 */}
        <ChatInput
          value={input}
          onChange={setInput}
          onSend={() => sendMessage(input)}
          onStop={stopStream}
          onKeyDown={onKeyDown}
          streaming={streaming}
          commands={commands}
          wfChips={WF_CHIPS}
          showWfChips={hasProjectContext}
          onWfChip={(prompt) => sendMessage(prompt)}
          attached={attached}
          uploading={uploading}
          uploadErr={uploadErr}
          modelSettings={modelSettings}
          selectedModel={selectedModel}
          thinkingLevel={thinkingLevel}
          onSelectModel={setSelectedModel}
          onSelectThinkingLevel={setThinkingLevel}
          onUpload={uploadFiles}
          canUpload={!workspaceReadonly}
          onRemoveAttachment={removeAttachment}
          onDropReference={referenceWorkspaceNode}
        />
      </div>

      {/* 当前空间面板 */}
      <WorkspacePanel
        title={workspaceTitle}
        readonly={workspaceReadonly}
        readonlyReason={workspaceReadonlyReason}
        nodes={workspace}
        loading={wsLoading}
        error={wsErr}
        collapsed={workspaceCollapsed}
        onToggle={() => setWorkspaceCollapsed((v) => !v)}
        onRefresh={loadWorkspace}
        onReference={referenceWorkspaceNode}
        onPreview={openPreview}
        onMoveTo={moveWorkspaceNode}
        onOpenDetail={onOpenWorkspaceDetail}
      />
      {previewPath && (
        <PreviewModal
          path={previewPath}
          name={previewName}
          workspaceApi={workspaceApi}
          onClose={closePreview}
          onDownload={() => triggerDownload(workspaceApi.downloadUrl(previewPath))}
        />
      )}
    </div>
  );
}

// ============ 子组件:消息轮 ============
function TurnView({ turn, username }: { turn: Turn; username: string }) {
  const [copied, setCopied] = useState(false);
  // AI 草稿「待采纳」卡片的采纳/驳回状态（M3.1.4）。key = `${entityType}:${draftId}`
  const [draftAction, setDraftAction] = useState<
    Record<
      string,
      { status: "adopting" | "adopted" | "rejected" | "error"; message?: string }
    >
  >({});

  const handleAdoptDraft = useCallback(async (part: DraftPart) => {
    setDraftAction((s) => ({ ...s, [part.id]: { status: "adopting" } }));
    try {
      const res = await api.adoptDraft(part.projectId, part.entityType, part.draftId);
      setDraftAction((s) => ({
        ...s,
        [part.id]: { status: "adopted", message: res.message || "采纳成功" },
      }));
    } catch (e) {
      setDraftAction((s) => ({
        ...s,
        [part.id]: {
          status: "error",
          message: e instanceof Error ? e.message : "采纳失败",
        },
      }));
    }
  }, []);

  const handleRejectDraft = useCallback((part: DraftPart) => {
    // 驳回 = 暂不采纳（仅前端收起操作，草稿仍留存可于数据页后续采纳/到期清理）
    setDraftAction((s) => ({ ...s, [part.id]: { status: "rejected" } }));
  }, []);

  const copyText = turn.parts
    .map((p) => (p.kind === "text" ? p.text : ""))
    .join("");
  const copyMessage = useCallback(async () => {
    if (!copyText) return;
    await navigator.clipboard.writeText(copyText);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }, [copyText]);

  if (turn.kind === "user") {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          gap: 12,
          animation: "fadeUp 240ms",
        }}
      >
        <div
          style={{
            maxWidth: "72%",
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
            gap: 4,
          }}
        >
          <div
            style={{
              background: "var(--accent-soft)",
              color: "var(--ink)",
              padding: "10px 14px",
              borderRadius: "14px 14px 4px 14px",
              fontSize: 14,
              lineHeight: 1.55,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {copyText}
          </div>
          <CopyMessageButton copied={copied} onClick={copyMessage} align="end" />
        </div>
        <Avatar name={username} size={30} />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: 12, animation: "fadeUp 240ms" }}>
      <span
        style={{
          width: 30,
          height: 30,
          borderRadius: 999,
          flexShrink: 0,
          background: "var(--surface)",
          border: "1px solid var(--line)",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--accent)",
        }}
      >
        <I.Logo size={16} />
      </span>
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          gap: 10,
          paddingTop: 4,
        }}
      >
        {turn.parts.map((p, i) => {
          if (p.kind === "text") return <MarkdownView key={i} text={p.text} />;
          if (p.kind === "draft") {
            // AI 结构化草稿「待采纳」卡片（M3.1.4）
            const action = draftAction[p.id];
            const previewLabel: Record<string, string> = {
              object_count: "节点数",
              name: "姓名",
              role_type: "角色类型",
              visit_type: "类型",
              summary: "摘要",
            };
            const previewEntries = Object.entries(p.preview).filter(
              ([, v]) => v !== null && v !== undefined && v !== "",
            );
            return (
              <div
                key={i}
                style={{
                  border: "1px solid var(--line)",
                  borderRadius: 10,
                  background: "var(--bg-2)",
                  padding: 12,
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    fontSize: 13,
                    fontWeight: 600,
                    color: "var(--ink)",
                  }}
                >
                  <I.Sparkles size={14} style={{ color: "var(--accent)" }} />
                  <span>{p.entityLabel}</span>
                  <span
                    style={{
                      fontSize: 11,
                      padding: "2px 8px",
                      borderRadius: 10,
                      background: "var(--accent-soft)",
                      color: "var(--accent)",
                    }}
                  >
                    待采纳
                  </span>
                </div>
                {previewEntries.length > 0 && (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: 4,
                      fontSize: 12.5,
                      color: "var(--ink-2)",
                    }}
                  >
                    {previewEntries.map(([k, v]) => (
                      <div key={k} style={{ display: "flex", gap: 8 }}>
                        <span style={{ color: "var(--ink-4)", minWidth: 64 }}>
                          {previewLabel[k] ?? k}
                        </span>
                        <span style={{ flex: 1, wordBreak: "break-word" }}>
                          {String(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {action?.status === "adopted" ? (
                  <div
                    style={{
                      fontSize: 12.5,
                      color: "var(--success)",
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <I.Check size={14} /> {action.message}
                  </div>
                ) : action?.status === "rejected" ? (
                  <div style={{ fontSize: 12.5, color: "var(--ink-4)" }}>
                    已驳回（暂不采纳，草稿仍保留可后续处理）
                  </div>
                ) : action?.status === "error" ? (
                  <div
                    style={{
                      fontSize: 12.5,
                      color: "var(--danger)",
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <I.CircleAlert size={14} /> {action.message}
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      onClick={() => handleAdoptDraft(p)}
                      disabled={action?.status === "adopting"}
                      style={{
                        padding: "6px 14px",
                        borderRadius: 8,
                        border: "none",
                        cursor: action?.status === "adopting" ? "wait" : "pointer",
                        background: "var(--accent)",
                        color: "#fff",
                        fontSize: 13,
                        opacity: action?.status === "adopting" ? 0.6 : 1,
                      }}
                    >
                      {action?.status === "adopting" ? "采纳中…" : "采纳"}
                    </button>
                    <button
                      onClick={() => handleRejectDraft(p)}
                      style={{
                        padding: "6px 14px",
                        borderRadius: 8,
                        cursor: "pointer",
                        background: "transparent",
                        color: "var(--ink-2)",
                        border: "1px solid var(--line)",
                        fontSize: 13,
                      }}
                    >
                      驳回
                    </button>
                  </div>
                )}
              </div>
            );
          }
          if (p.kind === "tool")
            return (
              <ToolCall
                key={i}
                toolName={p.name}
                input={p.input}
                state={p.state}
                output={p.output}
                errorText={p.errorText}
              />
            );
          if (p.kind === "error")
            return (
              <div
                key={i}
                style={{
                  background: "var(--danger-soft)",
                  color: "var(--danger)",
                  padding: "8px 12px",
                  borderRadius: 8,
                  fontSize: 13,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <I.CircleAlert size={14} />
                {p.text}
              </div>
            );
          return null;
        })}
        <CopyMessageButton copied={copied} onClick={copyMessage} />
      </div>
    </div>
  );
}

function CopyMessageButton({
  copied,
  onClick,
  align = "start",
}: {
  copied: boolean;
  onClick: () => void;
  align?: "start" | "end";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={copied ? "已复制" : "复制消息"}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        alignSelf: align === "end" ? "flex-end" : "flex-start",
        width: 26,
        height: 26,
        justifyContent: "center",
        background: "transparent",
        border: "none",
        borderRadius: 6,
        color: copied ? "var(--success)" : "var(--ink-3)",
        cursor: "pointer",
        padding: 0,
      }}
    >
      {copied ? <I.Check size={14} /> : <I.Copy size={14} />}
    </button>
  );
}

function SearchableDropdown({
  label,
  placeholder,
  valueLabel,
  valueMeta,
  options,
  icon,
}: {
  label: string;
  placeholder: string;
  valueLabel: string;
  valueMeta?: string;
  options: Array<{
    key: string;
    label: string;
    meta?: string;
    icon?: ReactNode;
    color?: string;
    onSelect: () => void;
  }>;
  icon?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [keyword, setKeyword] = useState("");
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    if (!kw) return options;
    return options.filter((option) =>
      `${option.label} ${option.meta || ""}`.toLowerCase().includes(kw),
    );
  }, [keyword, options]);

  useEffect(() => {
    if (!open) return;
    // 自动聚焦搜索框
    requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
    const onPointerDown = (event: PointerEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  return (
    <div ref={wrapperRef} style={{ position: "relative" }}>
      <div style={{ marginBottom: 6, fontSize: 12, fontWeight: 600, color: "var(--ink-2)", display: "flex", alignItems: "center", gap: 5 }}>
        {icon}
        {label}
      </div>
      <button
        type="button"
        className="focus-ring"
        onClick={() => setOpen((next) => !next)}
        style={{
          width: "100%",
          height: 38,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          padding: "0 12px",
          border: "1px solid var(--line-2)",
          borderRadius: 10,
          background: "var(--surface)",
          color: "var(--ink)",
          cursor: "pointer",
          font: "inherit",
          fontSize: 13,
          transition: "border-color 140ms, box-shadow 140ms, background 140ms",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = "var(--line)";
          e.currentTarget.style.background = "var(--bg)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = "var(--line-2)";
          e.currentTarget.style.background = "var(--surface)";
        }}
      >
        <span
          style={{
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <span style={{ fontWeight: 500 }}>{valueLabel}</span>
          {valueMeta && (
            <span style={{ color: "var(--ink-3)", fontSize: 12 }}>{valueMeta}</span>
          )}
        </span>
        <I.ChevronDown
          size={14}
          style={{
            color: "var(--ink-4)",
            transition: "transform 180ms cubic-bezier(0.34, 1.56, 0.64, 1)",
            transform: open ? "rotate(180deg)" : "none",
          }}
        />
      </button>
      {open && (
        <div
          style={{
            ...dropdownMenuStyle,
            borderRadius: 12,
            boxShadow: "var(--shadow-lg)",
            animation: "filter-panel-enter 200ms cubic-bezier(0.16, 1, 0.3, 1)",
            marginTop: 6,
          }}
        >
          <div style={{ padding: 8 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                background: "var(--bg-2)",
                borderRadius: 8,
                padding: "0 10px",
                height: 32,
              }}
            >
              <I.Search size={13} style={{ color: "var(--ink-4)", flexShrink: 0 }} />
              <input
                ref={inputRef}
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder={placeholder}
                style={{
                  flex: 1,
                  border: "none",
                  outline: "none",
                  background: "transparent",
                  fontSize: 13,
                  color: "var(--ink)",
                  fontFamily: "inherit",
                  height: "100%",
                }}
              />
              {keyword && (
                <button
                  type="button"
                  onClick={() => setKeyword("")}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--ink-4)",
                    cursor: "pointer",
                    padding: 0,
                    display: "flex",
                    alignItems: "center",
                  }}
                >
                  <I.X size={13} />
                </button>
              )}
            </div>
          </div>
          <div style={{ maxHeight: 220, overflow: "auto", padding: "0 4px 4px" }}>
            {filtered.length === 0 && (
              <div style={{ ...dropdownEmptyStyle, textAlign: "center", padding: "16px 10px" }}>
                <I.Search size={20} style={{ color: "var(--ink-4)", marginBottom: 6 }} />
                <div>没有匹配项</div>
              </div>
            )}
            {filtered.map((option, idx) => {
              const isFirst = idx === 0;
              return (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => {
                    option.onSelect();
                    setOpen(false);
                    setKeyword("");
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = "var(--accent-soft)";
                    e.currentTarget.style.color = "var(--accent-2)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = "transparent";
                    e.currentTarget.style.color = "var(--ink)";
                  }}
                  style={{
                    width: "100%",
                    minHeight: 38,
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "8px 10px",
                    border: 0,
                    borderTop: isFirst ? "none" : "1px solid var(--line-2)",
                    background: "transparent",
                    color: "var(--ink)",
                    cursor: "pointer",
                    textAlign: "left",
                    font: "inherit",
                    fontSize: 13,
                    transition: "background 120ms, color 120ms",
                    borderRadius: isFirst ? "6px 6px 0 0" : 0,
                  }}
                >
                  {option.icon && (
                    <span style={{ flexShrink: 0, display: "flex", alignItems: "center" }}>
                      {option.icon}
                    </span>
                  )}
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span
                      style={{
                        display: "block",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        fontWeight: 500,
                      }}
                    >
                      {option.label}
                    </span>
                    {option.meta && (
                      <span style={{ display: "block", marginTop: 2, color: "var(--ink-3)", fontSize: 12 }}>
                        {option.meta}
                      </span>
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// 筛选条件芯片
// 智能体颜色池（为每个智能体分配一个固定的颜色）
const AGENT_COLORS = ["#B85C3C", "#5C8A56", "#C68A3E", "#4A7593", "#8B5C8A", "#9A4A2E"];
function getAgentColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return AGENT_COLORS[Math.abs(hash) % AGENT_COLORS.length];
}

function SessionFilterPanel({
  agents,
  workspaceOptions,
  agentId,
  workspace,
  workspaceLocked,
  onAgentChange,
  onWorkspaceChange,
  onClose,
}: {
  agents: Agent[];
  workspaceOptions: SessionWorkspaceFilter[];
  agentId: number | null;
  workspace: SessionWorkspaceFilter;
  workspaceLocked: boolean;
  onAgentChange: (id: number | null) => void;
  onWorkspaceChange: (workspace: SessionWorkspaceFilter) => void;
  onClose: () => void;
}) {
  const selectedAgent = agents.find((agent) => agent.id === agentId);
  return (
    <div
      style={{
        position: "absolute",
        zIndex: 40,
        top: "calc(100% + 8px)",
        left: 0,
        right: 0,
        padding: 14,
        background: "var(--surface)",
        border: "1px solid var(--line-2)",
        borderRadius: 14,
        boxShadow: "var(--shadow-lg)",
        display: "flex",
        flexDirection: "column",
        gap: 14,
        animation: "filter-panel-enter 220ms cubic-bezier(0.16, 1, 0.3, 1)",
      }}
    >
      {/* 面板标题 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          paddingBottom: 2,
        }}
      >
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: "var(--ink-3)",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          筛选会话
        </span>
        <button
          type="button"
          onClick={onClose}
          style={{
            background: "transparent",
            border: "none",
            color: "var(--ink-4)",
            cursor: "pointer",
            padding: 2,
            display: "flex",
            borderRadius: 4,
            transition: "color 120ms, background 120ms",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "var(--ink-2)";
            e.currentTarget.style.background = "var(--bg-2)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "var(--ink-4)";
            e.currentTarget.style.background = "transparent";
          }}
        >
          <I.X size={14} />
        </button>
      </div>

      <SearchableDropdown
        label="智能体"
        placeholder="搜索智能体"
        valueLabel={selectedAgent?.name || "全部智能体"}
        valueMeta={selectedAgent?.code}
        icon={<I.Brain size={13} style={{ color: "var(--accent)" }} />}
        options={[
          {
            key: "all",
            label: "全部智能体",
            icon: (
              <span
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: 999,
                  background: "var(--bg-3)",
                  border: "1px solid var(--line-2)",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 10,
                  color: "var(--ink-3)",
                  flexShrink: 0,
                }}
              >
                全
              </span>
            ),
            onSelect: () => onAgentChange(null),
          },
          ...agents.map((agent) => ({
            key: String(agent.id),
            label: agent.name,
            meta: agent.code,
            icon: (
              <span
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: 999,
                  background: `${getAgentColor(agent.name)}18`,
                  border: `1.5px solid ${getAgentColor(agent.name)}40`,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 10,
                  color: getAgentColor(agent.name),
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                {agent.name[0]?.toUpperCase() || "?"}
              </span>
            ),
            onSelect: () => onAgentChange(agent.id),
          })),
        ]}
      />
      <SearchableDropdown
        label="工作空间"
        placeholder="搜索工作空间"
        valueLabel={workspace.label}
        icon={
          workspace.kind === "team" ? (
            <I.Folders size={13} style={{ color: "var(--info)" }} />
          ) : workspace.kind === "personal" ? (
            <I.Folder size={13} style={{ color: "var(--success)" }} />
          ) : (
            <I.Search size={13} style={{ color: "var(--ink-3)" }} />
          )
        }
        options={workspaceOptions.map((option) => ({
          key: `${option.kind}:${option.id ?? "all"}`,
          label: option.label,
          meta:
            option.kind === "team"
              ? "团队空间"
              : option.kind === "personal"
              ? "个人空间"
              : "全部",
          icon:
            option.kind === "team" ? (
              <I.Folders size={14} style={{ color: "var(--info)", flexShrink: 0 }} />
            ) : option.kind === "personal" ? (
              <I.Folder size={14} style={{ color: "var(--success)", flexShrink: 0 }} />
            ) : (
              <span
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: 999,
                  background: "var(--bg-3)",
                  border: "1px solid var(--line-2)",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 10,
                  color: "var(--ink-3)",
                  flexShrink: 0,
                }}
              >
                全
              </span>
            ),
          onSelect: () => {
            if (!workspaceLocked) onWorkspaceChange(option);
          },
        }))}
      />
      <div style={{ display: "flex", gap: 8, marginTop: 2 }}>
        <Btn variant="primary" size="sm" onClick={onClose} block>
          完成
        </Btn>
      </div>
    </div>
  );
}

// ============ 子组件:空状态 ============
function EmptyState({
  agents,
  pickedAgentId,
  onPickAgent,
  workspaceOptions,
  workspace,
  onPickWorkspace,
  shareSession,
  onShareSessionChange,
  projectName,
}: {
  agents: Agent[];
  pickedAgentId: number | null;
  onPickAgent: (id: number) => void;
  workspaceOptions: WorkspaceChoice[];
  workspace: WorkspaceChoice;
  onPickWorkspace: (workspace: WorkspaceChoice) => void;
  shareSession: boolean;
  onShareSessionChange: (shared: boolean) => void;
  /** Topbar 已选项目（空状态待绑定）；null 表示普通会话 */
  projectName: string | null;
}) {
  const selectedAgent = agents.find((agent) => agent.id === pickedAgentId) || null;

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: 40,
        gap: 28,
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 14,
        }}
      >
        <span
          style={{
            width: 56,
            height: 56,
            borderRadius: 14,
            background: "var(--surface)",
            border: "1px solid var(--line)",
            color: "var(--accent)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <I.Logo size={30} />
        </span>
        <h2
          style={{
            fontFamily: "var(--serif)",
            fontSize: 26,
            fontWeight: 500,
          }}
        >
          您好，欢迎使用国科智能体平台!
        </h2>
        <div style={{ color: "var(--ink-3)", fontSize: 18 }}>
          {projectName
            ? `项目会话 · ${projectName}，直接描述需求或点击下方工作流开始`
            : "选择一个智能体，告诉我你要做什么"}
        </div>
      </div>

      {projectName && (
        <div
          style={{
            width: "min(560px, 100%)",
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "12px 16px",
            background: "var(--accent-soft)",
            border: "1px solid var(--accent-soft)",
            borderRadius: 12,
            color: "var(--accent-2)",
            fontSize: 13,
          }}
        >
          <I.Briefcase size={16} style={{ flexShrink: 0 }} />
          <span>
            新会话将关联项目 <b>{projectName}</b>，自动加载项目专属顾问 Agent（含 7 个工作流 Skill）。可在顶部切换或取消选择项目。
          </span>
        </div>
      )}

      <div
        style={{
          width: "min(560px, 100%)",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 12,
        }}
      >
        {!projectName && (
          <SearchableDropdown
            label="智能体"
            placeholder="搜索智能体"
            valueLabel={selectedAgent?.name || "选择智能体"}
            options={agents.map((agent) => ({
              key: String(agent.id),
              label: agent.name,
              meta: agent.is_default ? "默认" : agent.code,
              onSelect: () => onPickAgent(agent.id),
            }))}
          />
        )}
        <SearchableDropdown
          label="工作空间"
          placeholder="搜索工作空间"
          valueLabel={workspace.label}
          options={workspaceOptions.map((item) => ({
            key: `${item.kind}:${item.id ?? "personal"}`,
            label: item.label,
            meta: item.kind === "team" ? "团队空间" : "个人空间",
            onSelect: () => onPickWorkspace(item),
          }))}
        />
      </div>
      {workspace.kind === "team" && (
        <label
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            color: "var(--ink-2)",
            fontSize: 13,
          }}
        >
          <input
            type="checkbox"
            checked={shareSession}
            onChange={(event) => onShareSessionChange(event.target.checked)}
          />
          共享给团队成员
        </label>
      )}
    </div>
  );
}

// ============ 子组件:输入区 ============
function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  onKeyDown,
  streaming,
  commands,
  wfChips,
  showWfChips,
  onWfChip,
  attached,
  uploading,
  uploadErr,
  modelSettings,
  selectedModel,
  thinkingLevel,
  onSelectModel,
  onSelectThinkingLevel,
  onUpload,
  canUpload = true,
  onRemoveAttachment,
  onDropReference,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  onKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
  streaming: boolean;
  commands: AgentCommand[];
  /** 项目级会话可用的工作流快捷 chip（M3.4.1） */
  wfChips: WfChipDef[];
  /** 是否显示工作流 chip（仅项目上下文） */
  showWfChips: boolean;
  /** 点击 chip：发送 `/${command} ${hint}` 触发对应 Skill */
  onWfChip: (prompt: string) => void;
  attached: UploadedFile[];
  uploading: boolean;
  uploadErr: string | null;
  modelSettings: ModelSettings | null;
  selectedModel: string | null;
  thinkingLevel: ThinkingLevelValue;
  onSelectModel: (model: string | null) => void;
  onSelectThinkingLevel: (level: ThinkingLevelValue) => void;
  onUpload: (files: FileList | File[]) => void;
  canUpload?: boolean;
  onRemoveAttachment: (path: string) => void;
  onDropReference?: (node: WorkspaceNode) => void;
}) {
  const ta = useRef<HTMLTextAreaElement | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const modelPickerRef = useRef<HTMLDivElement | null>(null);
  const thinkingPickerRef = useRef<HTMLDivElement | null>(null);

  const [commandActiveIndex, setCommandActiveIndex] = useState(0);
  const [commandMenuDismissed, setCommandMenuDismissed] = useState(false);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [thinkingMenuOpen, setThinkingMenuOpen] = useState(false);
  const [cursorPosition, setCursorPosition] = useState(value.length);
  const [dragOver, setDragOver] = useState(false);
  const commandTrigger = useMemo(
    () => getCommandTrigger(value, cursorPosition),
    [cursorPosition, value],
  );
  const commandQuery = commandTrigger?.query.toLowerCase() ?? "";
  const filteredCommands = useMemo(() => {
    if (!commandTrigger) return [];
    if (!commandQuery) return commands;
    return commands.filter((command) =>
      command.name.toLowerCase().includes(commandQuery),
    );
  }, [commands, commandQuery, commandTrigger]);
  const commandMenuOpen =
    commandTrigger !== null &&
    !streaming &&
    !commandMenuDismissed &&
    filteredCommands.length > 0;
  const visibleCommands = filteredCommands.slice(0, 10);
  const currentThinking = modelSettings?.thinking_levels.find(
    (level) => level.value === thinkingLevel,
  );
  const currentModelLabel = selectedModel || modelSettings?.default_model || "默认模型";

  useEffect(() => {
    if (commandActiveIndex >= visibleCommands.length) {
      setCommandActiveIndex(0);
    }
  }, [commandActiveIndex, visibleCommands.length]);

  useEffect(() => {
    if (!modelMenuOpen && !thinkingMenuOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node) {
        if (
          modelPickerRef.current &&
          !modelPickerRef.current.contains(target)
        ) {
          setModelMenuOpen(false);
        }
        if (
          thinkingPickerRef.current &&
          !thinkingPickerRef.current.contains(target)
        ) {
          setThinkingMenuOpen(false);
        }
      }
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [modelMenuOpen, thinkingMenuOpen]);

  useEffect(() => {
    if (streaming) {
      setModelMenuOpen(false);
      setThinkingMenuOpen(false);
    }
  }, [streaming]);

  useEffect(() => {
    if (!commandMenuOpen || !menuRef.current) return;
    const btns = menuRef.current.querySelectorAll("button");
    const target = btns[commandActiveIndex];
    if (target) {
      target.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [commandActiveIndex, commandMenuOpen]);

  // 自适应高度
  useEffect(() => {
    const el = ta.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [value]);

  useEffect(() => {
    setCommandActiveIndex(0);
    setCommandMenuDismissed(false);
  }, [cursorPosition, value]);

  const insertCommand = (name: string) => {
    if (!commandTrigger) return;
    const nextValue = replaceCommandTrigger(value, commandTrigger, name);
    const nextCursor = commandTrigger.start + name.length + 2;
    onChange(nextValue);
    setCursorPosition(nextCursor);
    setCommandMenuDismissed(true);
    requestAnimationFrame(() => {
      ta.current?.focus();
      ta.current?.setSelectionRange(nextCursor, nextCursor);
    });
  };

  // 触发隐藏的 file input
  const pickFiles = () => {
    if (uploading || streaming) return;
    fileInput.current?.click();
  };

  const handleTextareaKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (isInputComposing(e)) return;
    if (commandMenuOpen) {
      if (e.key === "ArrowDown" && visibleCommands.length > 0) {
        e.preventDefault();
        setCommandActiveIndex((idx) => (idx + 1) % visibleCommands.length);
        return;
      }
      if (e.key === "ArrowUp" && visibleCommands.length > 0) {
        e.preventDefault();
        setCommandActiveIndex((idx) =>
          idx === 0 ? visibleCommands.length - 1 : idx - 1,
        );
        return;
      }
      if (isCommandSelectionKey(e.key) && visibleCommands.length > 0) {
        e.preventDefault();
        const idx = Math.min(commandActiveIndex, visibleCommands.length - 1);
        insertCommand(visibleCommands[idx].name);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setCommandMenuDismissed(true);
        return;
      }
    }
    onKeyDown(e);
  };

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const fs = e.target.files;
    if (fs && fs.length > 0) {
      onUpload(fs);
    }
    // 清空 input,使得再次选中同一文件也能触发 change
    e.target.value = "";
  };

  // 发送按钮启用条件:非流式、非上传中、且文本或附件至少一项非空
  const canSend = !streaming && !uploading && (value.trim() !== "" || attached.length > 0);

  return (
    <div
      style={{
        padding: "12px 24px 18px",
        borderTop: "1px solid var(--line)",
        background: "var(--bg)",
        flexShrink: 0,
      }}
    >
      {/* 工作流快捷 chip（M3.4.1）：仅项目级会话显示，点击向会话发送 /skill-name 触发对应 Skill */}
      {showWfChips && wfChips.length > 0 && (
        <div
          style={{
            maxWidth: 820,
            margin: "0 auto 10px",
            display: "flex",
            flexWrap: "wrap",
            gap: 6,
          }}
        >
          {wfChips.map((chip) => (
            <button
              key={chip.key}
              type="button"
              disabled={streaming}
              onClick={() => onWfChip(`/${chip.command} ${chip.hint}`)}
              title={`/${chip.command}`}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                height: 30,
                padding: "0 12px",
                background: "var(--surface)",
                border: "1px solid var(--line)",
                borderRadius: 999,
                color: "var(--ink-2)",
                cursor: streaming ? "not-allowed" : "pointer",
                fontSize: 12.5,
                fontWeight: 500,
                fontFamily: "inherit",
                opacity: streaming ? 0.55 : 1,
                transition: "border-color 140ms, color 140ms, background 140ms",
              }}
              onMouseEnter={(e) => {
                if (streaming) return;
                e.currentTarget.style.borderColor = "var(--accent-soft)";
                e.currentTarget.style.color = "var(--accent-2)";
                e.currentTarget.style.background = "var(--accent-soft)";
              }}
              onMouseLeave={(e) => {
                if (streaming) return;
                e.currentTarget.style.borderColor = "var(--line)";
                e.currentTarget.style.color = "var(--ink-2)";
                e.currentTarget.style.background = "var(--surface)";
              }}
            >
              <chip.Icon size={13} style={{ flexShrink: 0 }} />
              <span>{chip.label}</span>
            </button>
          ))}
        </div>
      )}
      <div
        style={{
          maxWidth: 820,
          margin: "0 auto",
          background: "var(--surface)",
          border: dragOver
            ? "1px dashed var(--accent)"
            : "1px solid var(--line)",
          borderRadius: 14,
          padding: 12,
          boxShadow: "var(--shadow-sm)",
          transition: "border-color 120ms",
        }}
        onDragOver={(e) => {
          if (!onDropReference) return;
          if (
            Array.from(e.dataTransfer.types).includes(WORKSPACE_REF_DRAG_TYPE)
          ) {
            e.preventDefault();
            e.dataTransfer.dropEffect = "copy";
            setDragOver(true);
          }
        }}
        onDragLeave={(e) => {
          if (
            !e.currentTarget.contains(e.relatedTarget as Node | null)
          ) {
            setDragOver(false);
          }
        }}
        onDrop={(e) => {
          if (!onDropReference) return;
          setDragOver(false);
          e.preventDefault();
          const raw = e.dataTransfer.getData(WORKSPACE_REF_DRAG_TYPE);
          if (raw) {
            try {
              const node = JSON.parse(raw) as WorkspaceNode;
              onDropReference(node);
            } catch {
              /* ignore parse error */
            }
          }
        }}
      >
        {/* 附件错误提示 */}
        {uploadErr && (
          <div
            style={{
              background: "var(--danger-soft)",
              color: "var(--danger)",
              padding: "6px 10px",
              borderRadius: 8,
              fontSize: 12.5,
              marginBottom: 8,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <I.CircleAlert size={13} />
            {uploadErr}
          </div>
        )}

        {/* 已上传附件 chips */}
        {attached.length > 0 && (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 6,
              marginBottom: 8,
            }}
          >
            {attached.map((f) => (
              <span
                key={f.path}
                title={f.path}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "4px 6px 4px 10px",
                  background: "var(--bg-2)",
                  border: "1px solid var(--line)",
                  borderRadius: 999,
                  fontSize: 12.5,
                  color: "var(--ink-2)",
                  maxWidth: 280,
                }}
              >
                <I.Paperclip size={12} />
                <span
                  style={{
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    flex: 1,
                  }}
                >
                  {f.name}
                </span>
                <span
                  style={{
                    fontSize: 11,
                    color: "var(--ink-3)",
                    flexShrink: 0,
                  }}
                >
                  {formatBytes(f.size)}
                </span>
                <button
                  onClick={() => onRemoveAttachment(f.path)}
                  title="移除"
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--ink-3)",
                    cursor: "pointer",
                    padding: 0,
                    width: 16,
                    height: 16,
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    borderRadius: 999,
                    flexShrink: 0,
                  }}
                >
                  <I.X size={12} />
                </button>
              </span>
            ))}
          </div>
        )}

        {commandMenuOpen && (
          <div
            ref={menuRef}
            style={{
              marginBottom: 8,
              border: "1px solid var(--line)",
              borderRadius: 10,
              background: "var(--bg)",
              boxShadow: "var(--shadow-sm)",
              overflow: "auto",
              maxHeight: 320,
            }}
          >
            {visibleCommands.map((command, idx) => {
                const active = idx === commandActiveIndex;
                return (
                  <button
                    key={command.name}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => insertCommand(command.name)}
                    style={{
                      width: "100%",
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "9px 10px",
                      border: "none",
                      borderBottom:
                        idx === visibleCommands.length - 1
                          ? "none"
                          : "1px solid var(--line)",
                      background: active ? "var(--accent-soft)" : "transparent",
                      color: "var(--ink)",
                      cursor: "pointer",
                      textAlign: "left",
                      fontFamily: "inherit",
                    }}
                  >
                    <span
                      style={{
                        flex: 1,
                        minWidth: 0,
                        fontSize: 13,
                        fontWeight: 600,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      /{command.name}
                    </span>
                    <Tag tone={command.source === "plugin" ? "accent" : "neutral"}>
                      {command.source === "plugin"
                        ? "插件"
                        : command.source === "personal_skill"
                          ? "个人技能"
                          : "技能"}
                    </Tag>
                  </button>
                );
              })}
          </div>
        )}

        <textarea
          ref={ta}
          value={value}
          onChange={(e) => {
            setCursorPosition(e.target.selectionStart);
            onChange(e.target.value);
          }}
          onClick={(e) => setCursorPosition(e.currentTarget.selectionStart)}
          onKeyDown={handleTextareaKeyDown}
          onKeyUp={(e) => setCursorPosition(e.currentTarget.selectionStart)}
          onSelect={(e) => setCursorPosition(e.currentTarget.selectionStart)}
          placeholder="输入/调用技能"
          rows={1}
          style={{
            width: "100%",
            border: "none",
            outline: "none",
            resize: "none",
            background: "transparent",
            fontSize: 14,
            lineHeight: 1.55,
            color: "var(--ink)",
            fontFamily: "inherit",
            minHeight: 22,
            maxHeight: 160,
          }}
        />

        {/* 隐藏的文件选择器 */}
        <input
          ref={fileInput}
          type="file"
          multiple
          onChange={onFileChange}
          style={{ display: "none" }}
        />

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginTop: 8,
            gap: 8,
            fontSize: 11,
            color: "var(--ink-3)",
          }}
        >
          {/* 左侧:附件与模型设置 */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              flexWrap: "wrap",
            }}
          >
            {canUpload && (
              <button
                onClick={pickFiles}
                disabled={uploading || streaming}
                title={uploading ? "上传中…" : "添加附件文件"}
                className="focus-ring"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  padding: "4px 8px",
                  background: "transparent",
                  border: "1px solid var(--line)",
                  borderRadius: 8,
                  color: uploading ? "var(--ink-4)" : "var(--ink-3)",
                  cursor: uploading || streaming ? "not-allowed" : "pointer",
                  fontSize: 12,
                  fontFamily: "inherit",
                  transition: "background 120ms, color 120ms",
                }}
                onMouseEnter={(e) => {
                  if (!uploading && !streaming) {
                    e.currentTarget.style.background = "var(--bg-2)";
                    e.currentTarget.style.color = "var(--ink-2)";
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                  e.currentTarget.style.color = uploading
                    ? "var(--ink-4)"
                    : "var(--ink-3)";
                }}
              >
                {uploading ? (
                  <I.Loader size={12} />
                ) : (
                  <I.Paperclip size={12} />
                )}
                <span>{uploading ? "上传中…" : "附件"}</span>
              </button>
            )}
            {modelSettings && modelSettings.models.length > 0 && (
              <div ref={modelPickerRef} style={modelControlStyle}>
                <button
                  type="button"
                  className="focus-ring"
                  disabled={streaming}
                  title="选择模型"
                  onClick={() => {
                    setThinkingMenuOpen(false);
                    setModelMenuOpen((open) => !open);
                  }}
                  style={{
                    ...controlPillStyle,
                    minWidth: 196,
                    maxWidth: 260,
                    cursor: streaming ? "not-allowed" : "pointer",
                    opacity: streaming ? 0.62 : 1,
                  }}
                  onMouseEnter={(e) => {
                    if (streaming) return;
                    e.currentTarget.style.borderColor = "var(--accent)";
                    e.currentTarget.style.color = "var(--ink)";
                    e.currentTarget.style.transform = "translateY(-1px)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "var(--line)";
                    e.currentTarget.style.color = "var(--ink-2)";
                    e.currentTarget.style.transform = "none";
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: 999,
                      background: "var(--success)",
                      boxShadow: "0 0 0 3px var(--success-soft)",
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ color: "var(--ink-3)", fontSize: 11 }}>
                    模型
                  </span>
                  <span
                    style={{
                      flex: 1,
                      minWidth: 0,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      fontWeight: 700,
                      color: "var(--ink)",
                    }}
                  >
                    {currentModelLabel}
                  </span>
                  <I.ChevronDown
                    size={12}
                    style={{
                      transform: modelMenuOpen ? "rotate(180deg)" : "none",
                      transition: "transform 140ms",
                      flexShrink: 0,
                    }}
                  />
                </button>
                {modelMenuOpen && (
                  <div style={modelMenuStyle}>
                    <div
                      style={{
                        padding: "5px 8px 7px",
                        color: "var(--ink-3)",
                        fontSize: 11,
                        fontWeight: 700,
                      }}
                    >
                      选择 Claude Agent 模型
                    </div>
                    {modelSettings.models.map((model) => {
                      const active = model === selectedModel;
                      return (
                        <button
                          key={model}
                          type="button"
                          onClick={() => {
                            onSelectModel(model);
                            setModelMenuOpen(false);
                          }}
                          style={{
                            width: "100%",
                            display: "flex",
                            alignItems: "center",
                            gap: 9,
                            padding: "9px 10px",
                            border: "none",
                            borderRadius: 9,
                            background: active ? "var(--accent-soft)" : "transparent",
                            color: active ? "var(--accent-2)" : "var(--ink-2)",
                            cursor: "pointer",
                            textAlign: "left",
                            fontFamily: "inherit",
                            fontSize: 12.5,
                            fontWeight: active ? 700 : 500,
                          }}
                        >
                          <span
                            style={{
                              width: 18,
                              height: 18,
                              borderRadius: 999,
                              display: "inline-flex",
                              alignItems: "center",
                              justifyContent: "center",
                              color: active ? "var(--accent-2)" : "var(--ink-4)",
                              background: active ? "var(--surface)" : "var(--bg-2)",
                              flexShrink: 0,
                            }}
                          >
                            {active ? <I.Check size={12} /> : <I.Sparkles size={11} />}
                          </span>
                          <span
                            style={{
                              flex: 1,
                              minWidth: 0,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {model}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
            {modelSettings && (
              <div ref={thinkingPickerRef} style={modelControlStyle}>
                <button
                  type="button"
                  className="focus-ring"
                  disabled={streaming}
                  title="选择思考级别"
                  onClick={() => {
                    setModelMenuOpen(false);
                    setThinkingMenuOpen((open) => !open);
                  }}
                  style={{
                    ...controlPillStyle,
                    minWidth: 112,
                    cursor: streaming ? "not-allowed" : "pointer",
                    opacity: streaming ? 0.62 : 1,
                  }}
                  onMouseEnter={(e) => {
                    if (streaming) return;
                    e.currentTarget.style.borderColor = "var(--accent)";
                    e.currentTarget.style.color = "var(--ink)";
                    e.currentTarget.style.transform = "translateY(-1px)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "var(--line)";
                    e.currentTarget.style.color = "var(--ink-2)";
                    e.currentTarget.style.transform = "none";
                  }}
                >
                  <I.Activity size={13} style={{ color: "var(--accent)" }} />
                  <span style={{ color: "var(--ink-3)", fontSize: 11 }}>
                    思考
                  </span>
                  <span
                    style={{
                      minWidth: 20,
                      fontWeight: 700,
                      color: "var(--ink)",
                    }}
                  >
                    {currentThinking?.label ?? "关闭"}
                  </span>
                  <I.ChevronDown
                    size={12}
                    style={{
                      transform: thinkingMenuOpen ? "rotate(180deg)" : "none",
                      transition: "transform 140ms",
                    }}
                  />
                </button>
                {thinkingMenuOpen && (
                  <div
                    style={{
                      ...modelMenuStyle,
                      minWidth: 168,
                      maxWidth: 220,
                    }}
                  >
                    <div
                      style={{
                        padding: "5px 8px 7px",
                        color: "var(--ink-3)",
                        fontSize: 11,
                        fontWeight: 700,
                      }}
                    >
                      选择思考级别
                    </div>
                    {modelSettings.thinking_levels.map((level) => {
                      const active = level.value === thinkingLevel;
                      return (
                        <button
                          key={level.value}
                          type="button"
                          onClick={() => {
                            onSelectThinkingLevel(level.value);
                            setThinkingMenuOpen(false);
                          }}
                          style={{
                            width: "100%",
                            display: "flex",
                            alignItems: "center",
                            gap: 9,
                            padding: "9px 10px",
                            border: "none",
                            borderRadius: 9,
                            background: active ? "var(--accent-soft)" : "transparent",
                            color: active ? "var(--accent-2)" : "var(--ink-2)",
                            cursor: "pointer",
                            textAlign: "left",
                            fontFamily: "inherit",
                            fontSize: 12.5,
                            fontWeight: active ? 700 : 500,
                          }}
                        >
                          <span
                            style={{
                              width: 18,
                              height: 18,
                              borderRadius: 999,
                              display: "inline-flex",
                              alignItems: "center",
                              justifyContent: "center",
                              color: active ? "var(--accent-2)" : "var(--ink-4)",
                              background: active ? "var(--surface)" : "var(--bg-2)",
                              flexShrink: 0,
                            }}
                          >
                            {active ? <I.Check size={12} /> : <I.Activity size={11} />}
                          </span>
                          <span>{level.label}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 右侧:快捷键提示 + 发送/停止按钮 */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span>
              <Kbd>↩</Kbd> 发送 · <Kbd>⇧↩</Kbd> 换行
            </span>
            {streaming ? (
              <Btn
                variant="danger"
                size="sm"
                icon={<I.Stop size={12} />}
                onClick={onStop}
              >
                停止
              </Btn>
            ) : (
              <Btn
                variant="primary"
                size="sm"
                icon={<I.Send size={12} />}
                onClick={onSend}
                disabled={!canSend}
              >
                发送
              </Btn>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ 子组件:当前空间面板 ============
function WorkspacePanel({
  title,
  readonly = false,
  readonlyReason,
  nodes,
  loading,
  error,
  collapsed,
  onToggle,
  onRefresh,
  onReference,
  onPreview,
  onMoveTo,
  onOpenDetail,
}: {
  title: string;
  readonly?: boolean;
  readonlyReason?: string | null;
  nodes: WorkspaceNode[];
  loading: boolean;
  error: string | null;
  collapsed: boolean;
  onToggle: () => void;
  onRefresh: () => void;
  onReference: (node: WorkspaceNode) => void;
  onPreview: (node: WorkspaceNode) => void;
  onMoveTo?: (node: WorkspaceNode, targetDir: string) => void;
  onOpenDetail?: () => void;
}) {
  // 展开状态:记录已展开目录的相对路径,顶层目录默认展开方便快速查看
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  // 拖拽放置目标高亮
  const [activeDropPath, setActiveDropPath] = useState<string | null>(null);
  const [panelWidth, setPanelWidth] = useState(WORKSPACE_PANEL_DEFAULT_WIDTH);
  const [resizingPanel, setResizingPanel] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!resizingPanel) return;
    const onMouseMove = (e: MouseEvent) => {
      const right = panelRef.current?.getBoundingClientRect().right ?? window.innerWidth;
      setPanelWidth(clampWorkspacePanelWidth(right - e.clientX));
    };
    const onMouseUp = () => setResizingPanel(false);
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [resizingPanel]);

  // 顶层目录在数据更新后自动展开,但保留用户手动折叠/展开的选择
  useEffect(() => {
    setExpanded((prev) => {
      const next = new Set(prev);
      for (const n of nodes) {
        if (n.type === "dir") next.add(n.path);
      }
      return next;
    });
  }, [nodes]);

  const toggle = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  if (collapsed) {
    return (
      <div
        style={{
          width: 40,
          background: "var(--bg-2)",
          borderLeft: "1px solid var(--line)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          paddingTop: 12,
          flexShrink: 0,
        }}
      >
        <button
          onClick={onToggle}
          title={`展开${title}`}
          style={{
            background: "transparent",
            border: "none",
            color: "var(--ink-3)",
            cursor: "pointer",
            padding: 4,
            display: "flex",
          }}
        >
          <I.ChevronLeft size={16} />
        </button>
      </div>
    );
  }

  return (
    <>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="调整文件树宽度"
        tabIndex={0}
        title="拖拽调整文件树宽度"
        onMouseDown={(e) => {
          e.preventDefault();
          setResizingPanel(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") {
            e.preventDefault();
            setPanelWidth((width) => clampWorkspacePanelWidth(width + 16));
          }
          if (e.key === "ArrowRight") {
            e.preventDefault();
            setPanelWidth((width) => clampWorkspacePanelWidth(width - 16));
          }
        }}
        style={{
          width: 6,
          flex: "0 0 6px",
          cursor: "col-resize",
          background: resizingPanel ? "var(--accent-soft)" : "transparent",
          borderLeft: resizingPanel ? "1px solid var(--accent)" : "1px solid transparent",
        }}
      />
      <div
        ref={panelRef}
        style={{
          width: panelWidth,
          flex: `0 0 ${panelWidth}px`,
          background: "var(--bg-2)",
          borderLeft: "1px solid var(--line)",
          display: "flex",
          flexDirection: "column",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            height: 48,
            padding: "0 12px 0 16px",
            borderBottom: "1px solid var(--line)",
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexShrink: 0,
          }}
        >
          <I.Folder size={14} />
          <div
            style={{
              flex: 1,
              fontSize: 13,
              fontWeight: 600,
              color: "var(--ink)",
            }}
          >
            {title}
          </div>
          {readonly && (
            <span
              title={readonlyReason || "当前空间只读"}
              style={{
                color: "var(--ink-3)",
                fontSize: 11,
                border: "1px solid var(--line)",
                borderRadius: 999,
                padding: "2px 6px",
                background: "var(--bg)",
              }}
            >
              只读
            </span>
          )}
          {onOpenDetail && (
            <button
              onClick={onOpenDetail}
              title="进入空间详情"
              className="focus-ring"
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: 28,
                height: 28,
                background: "transparent",
                border: "1px solid var(--line)",
                borderRadius: 6,
                color: "var(--ink-3)",
                cursor: "pointer",
                transition: "background 120ms, color 120ms",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--bg-3)";
                e.currentTarget.style.color = "var(--ink)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "var(--ink-3)";
              }}
            >
              <I.ExternalLink size={13} />
            </button>
          )}
          <button
            onClick={onRefresh}
            disabled={loading}
            title="刷新"
            className="focus-ring"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 28,
              height: 28,
              background: "transparent",
              border: "1px solid var(--line)",
              borderRadius: 6,
              color: "var(--ink-3)",
              cursor: loading ? "default" : "pointer",
              transition: "background 120ms, color 120ms",
            }}
            onMouseEnter={(e) => {
              if (!loading) {
                e.currentTarget.style.background = "var(--bg-3)";
                e.currentTarget.style.color = "var(--ink)";
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = "var(--ink-3)";
            }}
          >
            {loading ? <I.Loader size={13} /> : <I.Refresh size={13} />}
          </button>
        <button
          onClick={onToggle}
          title="收起"
          className="focus-ring"
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 28,
            height: 28,
            background: "transparent",
            border: "1px solid var(--line)",
            borderRadius: 6,
            color: "var(--ink-3)",
            cursor: "pointer",
            transition: "background 120ms, color 120ms",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "var(--bg-3)";
            e.currentTarget.style.color = "var(--ink)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.color = "var(--ink-3)";
          }}
        >
          <I.ChevronRight size={16} />
        </button>
      </div>

      {/* 树体 */}
      <div
        style={{ flex: 1, overflow: "auto", padding: "6px 4px 16px" }}
        onDragOver={(e) => {
          if (readonly) return;
          e.preventDefault();
          setActiveDropPath(null);
          e.dataTransfer.dropEffect = e.dataTransfer.types.includes(WORKSPACE_DRAG_TYPE)
            ? "move"
            : "copy";
        }}
        onDragLeave={(e) => {
          if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
          setActiveDropPath(null);
        }}
        onDrop={(e) => {
          if (readonly) return;
          e.preventDefault();
          setActiveDropPath(null);
          const draggedNode = readDraggedWorkspaceNode(e.dataTransfer);
          if (draggedNode) {
            if (canMoveWorkspaceNode(draggedNode, "")) {
              onMoveTo?.(draggedNode, "");
            }
            return;
          }
        }}
      >
        {error && (
          <div
            style={{
              margin: "8px 10px",
              padding: "8px 10px",
              background: "var(--danger-soft)",
              color: "var(--danger)",
              borderRadius: 8,
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
        {!error && nodes.length === 0 && !loading && (
          <div
            style={{
              padding: 20,
              color: "var(--ink-3)",
              fontSize: 12.5,
              textAlign: "center",
              lineHeight: 1.6,
            }}
          >
            {title}为空
            <div style={{ fontSize: 11.5, marginTop: 4 }}>
              对话过程中创建或上传的文件会出现在这里
            </div>
          </div>
        )}
        {nodes.map((n) => (
          <TreeNode
            key={n.path}
            node={n}
            depth={0}
            expanded={expanded}
            onToggle={toggle}
            onReference={onReference}
            onPreview={onPreview}
            activeDropPath={activeDropPath}
            setActiveDropPath={setActiveDropPath}
            onMoveTo={onMoveTo}
            readonly={readonly}
          />
        ))}
      </div>
      </div>
    </>
  );
}

// 单个树节点(递归):目录可展开,文件展示名称与大小
// 悬停时右侧浮现"引用 / 删除"按钮;点击删除会在节点下方展开内联确认条
function TreeNode({
  node,
  depth,
  expanded,
  onToggle,
  onReference,
  onPreview,
  activeDropPath,
  setActiveDropPath,
  onMoveTo,
  readonly = false,
}: {
  node: WorkspaceNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string) => void;
  onReference: (node: WorkspaceNode) => void;
  onPreview: (node: WorkspaceNode) => void;
  activeDropPath: string | null;
  setActiveDropPath: (path: string | null) => void;
  onMoveTo?: (node: WorkspaceNode, targetDir: string) => void;
  readonly?: boolean;
}) {
  const isDir = node.type === "dir";
  const isOpen = isDir && expanded.has(node.path);
  // 左侧缩进:每层 14px,首列保留 chevron 占位
  const indent = 8 + depth * 14;
  const [hovered, setHovered] = useState(false);
  const showActions = hovered;
  const pressTimerRef = useRef<number | null>(null);
  const [dragEnabled, setDragEnabled] = useState(false);
  const dropActive = activeDropPath === node.path;
  const isWorkspaceDrag = (e: React.DragEvent) =>
    e.dataTransfer.types.includes(WORKSPACE_DRAG_TYPE);
  const clearPressTimer = () => {
    if (pressTimerRef.current !== null) {
      window.clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }
  };

  return (
    <>
      <div
        onClick={() => isDir && onToggle(node.path)}
        draggable={dragEnabled}
        onMouseDown={(e) => {
          if (readonly) return;
          if (e.button !== 0) return;
          clearPressTimer();
          pressTimerRef.current = window.setTimeout(() => {
            setDragEnabled(true);
          }, 50);
        }}
        onMouseUp={() => {
          clearPressTimer();
          setDragEnabled(false);
        }}
        onMouseLeave={() => {
          clearPressTimer();
          setDragEnabled(false);
          setHovered(false);
        }}
        onDragStart={(e) => {
          clearPressTimer();
          if (!dragEnabled) {
            e.preventDefault();
            return;
          }
          e.dataTransfer.effectAllowed = "copyMove";
          e.dataTransfer.setData(
            WORKSPACE_DRAG_TYPE,
            JSON.stringify({ path: node.path, name: node.name, type: node.type }),
          );
          e.dataTransfer.setData(
            WORKSPACE_REF_DRAG_TYPE,
            JSON.stringify({
              path: node.path,
              name: node.name,
              type: node.type,
              size: node.size,
              agent_path: node.agent_path ?? null,
            }),
          );
        }}
        onDragEnd={() => {
          clearPressTimer();
          setDragEnabled(false);
          setActiveDropPath(null);
        }}
        onDragEnter={(e) => {
          if (readonly) return;
          if (!isDir) return;
          e.preventDefault();
          e.stopPropagation();
          setActiveDropPath(node.path);
        }}
        onDragOver={(e) => {
          if (readonly) return;
          if (!isDir) {
            e.preventDefault();
            e.stopPropagation();
            setActiveDropPath(null);
            e.dataTransfer.dropEffect = "none";
            return;
          }
          e.preventDefault();
          e.stopPropagation();
          e.dataTransfer.dropEffect = isWorkspaceDrag(e) ? "move" : "copy";
          setActiveDropPath(node.path);
        }}
        onDrop={(e) => {
          if (readonly) return;
          e.preventDefault();
          e.stopPropagation();
          if (!isDir) return;
          setActiveDropPath(null);
          const draggedNode = readDraggedWorkspaceNode(e.dataTransfer);
          if (draggedNode) {
            if (canMoveWorkspaceNode(draggedNode, node.path)) {
              onMoveTo?.(draggedNode, node.path);
            }
            return;
          }
        }}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "4px 8px",
          paddingLeft: indent,
          fontSize: 13,
          color: "var(--ink)",
          cursor: dragEnabled ? "grab" : isDir ? "pointer" : "default",
          borderRadius: 6,
          userSelect: "none",
          background: dropActive
            ? "var(--accent-soft)"
            : hovered
              ? "var(--bg-3)"
              : "transparent",
          border: "1px solid",
          borderColor: dropActive ? "var(--accent)" : "transparent",
          boxShadow: dropActive ? "inset 0 0 0 1px var(--accent)" : "none",
        }}
        onMouseEnter={() => setHovered(true)}
      >
        {/* chevron 占位:文件没有展开能力,但保留位置让对齐一致 */}
        <span
          style={{
            width: 12,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--ink-3)",
            flexShrink: 0,
          }}
        >
          {isDir ? (
            isOpen ? (
              <I.ChevronDown size={11} />
            ) : (
              <I.ChevronRight size={11} />
            )
          ) : null}
        </span>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            color: isDir ? "var(--accent)" : "var(--ink-3)",
            flexShrink: 0,
          }}
        >
          {isDir ? (
            isOpen ? (
              <I.FolderOpen size={13} />
            ) : (
              <I.Folder size={13} />
            )
          ) : (
            <I.File size={13} />
          )}
        </span>
        <FileNameTooltip
          label={node.name}
          style={{
            flex: 1,
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            display: "block",
          }}
        >
          {node.name}
        </FileNameTooltip>
        {/* 文件大小:悬停时让位给动作按钮,避免拥挤 */}
        {!showActions && node.type === "file" && typeof node.size === "number" && (
          <span
            style={{
              fontSize: 11,
              color: "var(--ink-4)",
              flexShrink: 0,
            }}
          >
            {formatBytes(node.size)}
          </span>
        )}
        {/* 悬停动作:引用 + 删除 */}
        {showActions && (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 2,
              flexShrink: 0,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {!isDir && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onPreview(node);
                }}
                title="预览"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: 22,
                  height: 22,
                  background: "transparent",
                  border: "none",
                  color: "var(--ink-3)",
                  cursor: "pointer",
                  borderRadius: 4,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "var(--bg-2)";
                  e.currentTarget.style.color = "var(--accent)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                  e.currentTarget.style.color = "var(--ink-3)";
                }}
              >
                <I.Eye size={12} />
              </button>
            )}
            <button
              onClick={(e) => {
                e.stopPropagation();
                onReference(node);
              }}
              title={isDir ? "引用目录到输入框" : "引用文件到输入框"}
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: 22,
                height: 22,
                background: "transparent",
                border: "none",
                color: "var(--ink-3)",
                cursor: "pointer",
                borderRadius: 4,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--bg-2)";
                e.currentTarget.style.color = "var(--accent)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "var(--ink-3)";
              }}
            >
              <I.Paperclip size={12} />
            </button>
          </span>
        )}
      </div>
      {isOpen &&
        node.children &&
        node.children.map((c) => (
          <TreeNode
            key={c.path}
            node={c}
            depth={depth + 1}
            expanded={expanded}
            onToggle={onToggle}
            onReference={onReference}
            onPreview={onPreview}
            activeDropPath={activeDropPath}
            setActiveDropPath={setActiveDropPath}
            onMoveTo={onMoveTo}
            readonly={readonly}
          />
        ))}
    </>
  );
}

// ============ HTML 文件预览 ============
// 支持源码与渲染两种模式切换,使用 sandboxed iframe 安全渲染
function HtmlFilePreview({ text }: { text: string }) {
  const [renderMode, setRenderMode] = useState(true);
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button
          type="button"
          onClick={() => setRenderMode(false)}
          style={{
            padding: "2px 10px",
            fontSize: 12,
            borderRadius: 4,
            border: "1px solid var(--line)",
            background: renderMode ? "transparent" : "var(--bg-3)",
            color: renderMode ? "var(--ink-3)" : "var(--ink)",
            cursor: "pointer",
          }}
        >
          源码
        </button>
        <button
          type="button"
          onClick={() => setRenderMode(true)}
          style={{
            padding: "2px 10px",
            fontSize: 12,
            borderRadius: 4,
            border: "1px solid var(--line)",
            background: renderMode ? "var(--bg-3)" : "transparent",
            color: renderMode ? "var(--ink)" : "var(--ink-3)",
            cursor: "pointer",
          }}
        >
          渲染
        </button>
      </div>
      {renderMode ? (
        <iframe
          sandbox="allow-scripts"
          srcDoc={text}
          style={{
            width: "100%",
            height: "70vh",
            border: "1px solid var(--line)",
            borderRadius: 8,
            background: "var(--surface)",
          }}
        />
      ) : (
        <pre
          style={{
            margin: 0,
            width: "100%",
            fontSize: 13,
            fontFamily: "var(--font-mono, ui-monospace, monospace)",
            color: "var(--ink)",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {text}
        </pre>
      )}
    </div>
  );
}

// ============ 预览模态 ============
// 中央固定弹层;文本和可转换文档用 fetch 渲染,媒体类直接把 URL 给 src。
function PreviewModal({
  path,
  name,
  workspaceApi,
  onClose,
  onDownload,
}: {
  path: string;
  name: string;
  workspaceApi: WorkspaceApi;
  onClose: () => void;
  onDownload: () => void;
}) {
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const previewShellRef = useRef<HTMLDivElement | null>(null);
  const imageDragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [imageZoom, setImageZoom] = useState(1);
  const [imagePan, setImagePan] = useState({ x: 0, y: 0 });
  const preview = useWorkspacePreview(path, name, 0, "raw", workspaceApi);
  const loading = preview.loading;
  const previewError = errMsg || preview.error;
  const imagePreview = preview.category === "image";
  const documentPreview = preview.category === "office" || preview.category === "pdf";
  const documentPreviewUrl = documentPreview ? workspaceApi.officePreviewUrl(path) : "";
  const [documentLoading, setDocumentLoading] = useState(false);

  useEffect(() => {
    setErrMsg(null);
    setImageZoom(1);
    setImagePan({ x: 0, y: 0 });
    imageDragRef.current = null;
  }, [path, name]);

  useEffect(() => {
    setDocumentLoading(Boolean(documentPreviewUrl));
  }, [documentPreviewUrl]);

  useEffect(() => {
    if (!imagePreview) {
      setImageZoom(1);
      setImagePan({ x: 0, y: 0 });
      imageDragRef.current = null;
    }
  }, [imagePreview]);

  useEffect(() => {
    const onFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === previewShellRef.current);
    };
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  // ESC 关闭
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const toggleFullscreen = useCallback(async () => {
    const shell = previewShellRef.current;
    if (!shell) return;
    try {
      if (document.fullscreenElement === shell) {
        await document.exitFullscreen();
        return;
      }
      await shell.requestFullscreen();
    } catch {
      setErrMsg("当前浏览器不允许进入全屏预览");
    }
  }, []);

  const setZoom = useCallback((nextZoom: number) => {
    const clamped = Math.min(4, Math.max(0.5, Math.round(nextZoom * 100) / 100));
    setImageZoom(clamped);
    if (clamped <= 1) {
      setImagePan({ x: 0, y: 0 });
      imageDragRef.current = null;
    }
  }, []);

  const resetImageTransform = useCallback(() => {
    setImageZoom(1);
    setImagePan({ x: 0, y: 0 });
    imageDragRef.current = null;
  }, []);

  const startImageDrag = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (imageZoom <= 1) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    imageDragRef.current = {
      x: e.clientX,
      y: e.clientY,
      panX: imagePan.x,
      panY: imagePan.y,
    };
  }, [imagePan.x, imagePan.y, imageZoom]);

  const moveImageDrag = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = imageDragRef.current;
    if (!drag) return;
    setImagePan({
      x: drag.panX + e.clientX - drag.x,
      y: drag.panY + e.clientY - drag.y,
    });
  }, []);

  const endImageDrag = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (!imageDragRef.current) return;
    imageDragRef.current = null;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // 指针捕获可能已被浏览器释放。
    }
  }, []);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        ref={previewShellRef}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: isFullscreen ? "100vw" : "min(1100px, 90vw)",
          height: isFullscreen ? "100vh" : undefined,
          maxHeight: isFullscreen ? "none" : "85vh",
          background: "var(--surface)",
          boxShadow: "var(--shadow-lg)",
          border: "1px solid var(--line)",
          borderRadius: isFullscreen ? 0 : 12,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* 头部 */}
        <div
          style={{
            height: 48,
            padding: "0 12px 0 16px",
            borderBottom: "1px solid var(--line)",
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexShrink: 0,
          }}
        >
          <I.File size={14} />
          {imagePreview && !loading && !previewError && (
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                padding: "2px 4px",
                border: "1px solid var(--line)",
                borderRadius: 7,
                background: "var(--bg-2)",
              }}
            >
              <button
                onClick={() => setZoom(imageZoom - 0.25)}
                title="缩小"
                className="focus-ring"
                style={modalIconBtnStyle({ border: "none", width: 24, height: 24 })}
              >
                <I.Minus size={12} />
              </button>
              <span style={{ minWidth: 42, textAlign: "center", fontSize: 12, color: "var(--ink-3)" }}>
                {Math.round(imageZoom * 100)}%
              </span>
              <button
                onClick={() => setZoom(imageZoom + 0.25)}
                title="放大"
                className="focus-ring"
                style={modalIconBtnStyle({ border: "none", width: 24, height: 24 })}
              >
                <I.Plus size={12} />
              </button>
              <button
                onClick={resetImageTransform}
                title="重置缩放"
                className="focus-ring"
                style={modalIconBtnStyle({ border: "none", width: 24, height: 24 })}
              >
                <I.Refresh size={12} />
              </button>
            </div>
          )}
          <div
            style={{
              flex: 1,
              fontSize: 13,
              fontWeight: 600,
              color: "var(--ink)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={path}
          >
            {name}
          </div>
          <button
            onClick={toggleFullscreen}
            title={isFullscreen ? "退出全屏" : "全屏预览"}
            className="focus-ring"
            style={modalIconBtnStyle()}
          >
            <I.Maximize size={13} />
          </button>
          <button
            onClick={onDownload}
            title="下载"
            className="focus-ring"
            style={modalIconBtnStyle()}
          >
            <I.Download size={13} />
          </button>
          <button
            onClick={onClose}
            title="关闭"
            className="focus-ring"
            style={modalIconBtnStyle()}
          >
            <I.X size={13} />
          </button>
        </div>

        {/* 主体 */}
        <div
          style={{
            flex: 1,
            overflow: "auto",
            padding: imagePreview ? "24px 12px 12px" : 12,
            display: "flex",
            alignItems:
              imagePreview
                ? "flex-start"
                : preview.shouldFetchText ||
                    preview.category === "office" ||
                    preview.category === "pdf"
                  ? "stretch"
                  : "center",
            justifyContent: "center",
            background: "var(--bg-2)",
          }}
        >
          {loading && !documentPreview && <I.Loader size={20} />}
          {previewError && !loading && (
            <PreviewError msg={previewError} onDownload={onDownload} />
          )}
          {!previewError && !loading && documentPreview && (
            <div
              style={{
                position: "relative",
                width: "100%",
                height: isFullscreen
                  ? "calc(100vh - 96px)"
                  : "calc(85vh - 96px)",
              }}
            >
              {documentLoading && (
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "var(--ink-3)",
                    fontSize: 13,
                    background: "var(--bg-2)",
                    zIndex: 1,
                  }}
                >
                  文档加载中，请稍后。大文件首次加载耗时较长，请耐心等待。
                </div>
              )}
              <iframe
                key={documentPreviewUrl}
                src={documentPreviewUrl}
                onLoad={() => setDocumentLoading(false)}
                style={{
                  width: "100%",
                  height: "100%",
                  border: "none",
                  visibility: documentLoading ? "hidden" : "visible",
                }}
                title={name}
              />
            </div>
          )}
          {!previewError && !loading && preview.shouldFetchText && preview.text !== null && isTextualMime(preview.mime) && (
            isMarkdownPreview(name, preview.mime, preview.resolvedPath) ? (
              // Markdown 类型用与聊天消息一致的 MdView 渲染
              <div
                style={{ width: "100%", color: "var(--ink)" }}
                data-mime={preview.mime}
              >
                <MarkdownView text={preview.text} basePath={preview.resolvedPath || path} />
              </div>
            ) : isHtmlName(name) ? (
              <HtmlFilePreview text={preview.text} />
            ) : (
              <pre
                style={{
                  margin: 0,
                  width: "100%",
                  fontSize: 13,
                  fontFamily: "var(--font-mono, ui-monospace, monospace)",
                  color: "var(--ink)",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
                data-mime={preview.mime}
              >
                {preview.text}
              </pre>
            )
          )}
          {!previewError && !loading && preview.shouldFetchText && (preview.text === null || !isTextualMime(preview.mime)) && (
            <PreviewError
              msg="该类型不支持在线预览,请下载后查看。"
              onDownload={onDownload}
            />
          )}
          {!previewError && !loading && preview.category === "image" && (
            <div
              onPointerDown={startImageDrag}
              onPointerMove={moveImageDrag}
              onPointerUp={endImageDrag}
              onPointerCancel={endImageDrag}
              style={{
                width: "100%",
                minHeight: isFullscreen ? "calc(100vh - 96px)" : "calc(85vh - 96px)",
                display: "flex",
                alignItems: "flex-start",
                justifyContent: "center",
                overflow: "hidden",
                cursor: imageZoom > 1 ? "grab" : "default",
                touchAction: "none",
              }}
            >
              <img
                src={workspaceApi.previewUrl(path)}
                alt={name}
                draggable={false}
                style={{
                  maxWidth: "100%",
                  maxHeight: isFullscreen ? "calc(100vh - 96px)" : "calc(85vh - 96px)",
                  objectFit: "contain",
                  transform: `translate(${imagePan.x}px, ${imagePan.y}px) scale(${imageZoom})`,
                  transformOrigin: "center top",
                  transition: imageDragRef.current ? "none" : "transform 120ms ease",
                  userSelect: "none",
                  willChange: "transform",
                }}
                onError={() => setErrMsg("加载失败")}
              />
            </div>
          )}
          {!previewError && !loading && preview.category === "video" && (
            <video
              src={workspaceApi.previewUrl(path)}
              controls
              style={{ maxWidth: "100%", maxHeight: "70vh" }}
              onError={() => setErrMsg("加载失败")}
            />
          )}
          {!previewError && !loading && preview.category === "audio" && (
            <audio
              src={workspaceApi.previewUrl(path)}
              controls
              style={{ width: "100%" }}
              onError={() => setErrMsg("加载失败")}
            />
          )}
          {!previewError && !loading && preview.category === "unsupported" && !preview.shouldFetchText && (
            <PreviewError
              msg="该类型不支持在线预览,请下载后查看。"
              onDownload={onDownload}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function modalIconBtnStyle(overrides: CSSProperties = {}): CSSProperties {
  return {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: 28,
    height: 28,
    background: "transparent",
    border: "1px solid var(--line)",
    borderRadius: 6,
    color: "var(--ink-3)",
    cursor: "pointer",
    ...overrides,
  };
}

function PreviewError({
  msg,
  onDownload,
}: {
  msg: string;
  onDownload: () => void;
}) {
  return (
    <div
      style={{
        padding: 24,
        textAlign: "center",
        color: "var(--ink-2)",
        fontSize: 13,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 12,
      }}
    >
      <I.CircleAlert size={20} />
      <div>{msg}</div>
      <button
        onClick={onDownload}
        style={{
          padding: "6px 14px",
          background: "var(--accent)",
          color: "#fff",
          border: "none",
          borderRadius: 6,
          cursor: "pointer",
          fontSize: 12.5,
          fontFamily: "inherit",
        }}
      >
        下载文件
      </button>
    </div>
  );
}
