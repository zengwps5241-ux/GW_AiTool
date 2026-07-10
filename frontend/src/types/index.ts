// API 数据类型定义

export interface UserMe {
  id: number | null;
  username: string;
  phone?: string | null;
  status?: string;
  registration_source?: string;
  wechat_user_id?: string | null;
  display_name: string | null;
  avatar_url: string | null;
  department: string | null;
  department_ids?: number[] | null;
  position: string | null;
  mobile: string | null;
  email: string | null;
  auth_source: string;
  role: "super" | "admin" | "user";
}

export type WorkspaceKind = "personal" | "team";
export type TeamMemberRole = "reader" | "editor";

export interface TeamSpace {
  id: number;
  name: string;
  description: string | null;
  owner_user_id: number;
  owner_name: string;
  member_count: number;
  locked_by_user_id: number | null;
  locked_by_name: string | null;
  lock_acquired_at: string | null;
  lock_note: string | null;
  member_role: TeamMemberRole;
  can_write: boolean;
  is_owner: boolean;
  readonly_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface TeamSpaceMember {
  id: number;
  user_id: number;
  username: string;
  display_name: string | null;
  role: TeamMemberRole;
  is_owner: boolean;
  added_by_user_id: number;
  created_at: string;
  updated_at: string;
}

export interface TeamSpaceMemberSearchItem {
  user_id: number;
  username: string;
  display_name: string | null;
  is_member: boolean;
}

export interface Session {
  id: string;
  title: string;
  agent_id: number | null;
  agent_name: string | null;
  created_by_user_id: number | null;
  created_by_name: string | null;
  workspace_kind: WorkspaceKind;
  team_space_id: number | null;
  team_space_name: string | null;
  /** 项目级会话绑定的项目（M3.4.2）；普通会话为 null */
  project_id: number | null;
  project_name: string | null;
  is_shared: boolean;
  workspace_member_role: TeamMemberRole | null;
  workspace_can_write: boolean;
  workspace_readonly_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface Agent {
  id: number;
  name: string;
  code: string;
  system_prompt: string | null;
  skills: string;
  plugins: string;
  category_id: number;
  category: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface Skill {
  name: string;
  description: string;
  category: string;
}

/** 后端扫描到的本地插件,字段与 backend.app.schemas.PluginOut 对齐 */
export interface Plugin {
  name: string;
  version: string;
  description: string;
  /** 相对于 claude_data_dir/plugins 的 POSIX 路径,用作勾选/存储 key */
  path: string;
  category: string;
}

/** 分类 */
export interface Category {
  id: number;
  name: string;
}

/** 已上传文件的元数据,由后端 /api/uploads 返回 */
export interface UploadedFile {
  name: string;
  path: string;
  size: number;
  preview_path: string;
  agent_path: string;
  converted: boolean;
}

export type ThinkingLevelValue = "disabled" | "low" | "medium" | "high";

export interface ThinkingLevelOption {
  value: ThinkingLevelValue;
  label: string;
}

export interface ModelSettings {
  models: string[];
  thinking_levels: ThinkingLevelOption[];
  default_model: string | null;
  default_thinking_level: ThinkingLevelValue;
}

export interface ChatModelSelection {
  model?: string | null;
  thinking_level: ThinkingLevelValue;
}

export interface LoginWhitelistUser {
  id: number;
  name: string;
}

export interface LoginWhitelistDepartment {
  id: number;
  department_id: number;
  name: string;
  path: string;
}

export interface LoginWhitelistDepartmentSearchItem {
  department_id: number;
  name: string;
  path: string;
}

export interface LoginWhitelistConfig {
  users: LoginWhitelistUser[];
  departments: LoginWhitelistDepartment[];
}

/** 个人空间文件树节点 —— 与 backend.app.routes.workspace.WorkspaceNode 对齐 */
export interface WorkspaceNode {
  name: string;
  path: string;
  type: "file" | "dir";
  size?: number;
  mtime?: number;
  /** 已转换为 markdown 的源文件,这里给出 agent 应使用的 md 路径;未转换为 null */
  agent_path?: string | null;
  children?: WorkspaceNode[];
  conversion_status?: "queued" | "running" | "succeeded" | "failed" | null;
  conversion_task_id?: number | null;
  conversion_error?: string | null;
  markdown_path?: string | null;
}

/** SSE 事件类型 —— 与 backend.claude_runner 输出格式对齐 */
export type ChatEvent =
  | { type: "user_text"; text: string }
  | { type: "assistant_text"; text: string }
  | { type: "assistant_thinking"; text?: string }
  | {
      type: "tool_use";
      id: string;
      name: string;
      input: unknown;
    }
  | {
      type: "tool_result";
      tool_use_id: string;
      content: unknown;
      is_error?: boolean;
    }
  | {
      /** 草稿「待采纳」事件（M3.1.3 后端 handler 推送；M3.4.3 增量更新携带 is_update/revision/previous） */
      type: "draft_pending";
      entity_type: string;
      entity_label: string;
      draft_id: number;
      project_id: number;
      preview: Record<string, unknown>;
      /** 是否为增量更新（true=本次修订，携带 previous 供 diff，§7.2 Chat 调整） */
      is_update?: boolean;
      /** 草稿修订号（business_map 整图草稿：第 N 版） */
      revision?: number;
      /** 上一版内容快照（business_map 为整图 objects；stakeholder/visit 为字段快照） */
      previous?: Record<string, unknown>;
    }
  | { type: "result"; [key: string]: unknown }
  | { type: "error"; message: string };

/** 采纳结果（POST /api/projects/{id}/adopt，M2.4/M3.1.3） */
export interface AdoptResult {
  success: boolean;
  adopted_object_count: number;
  version_number: number;
  review_status: string;
  message?: string | null;
}

/** 带序号的运行事件,用于恢复运行中会话的 SSE 流 */
export interface RunEvent {
  seq: number;
  event: ChatEvent;
}

/** 运行中会话的恢复状态,与 /api/sessions/{id}/running 对齐 */
export interface RunningSessionState {
  running: boolean;
  run_id?: string;
  status: "running" | "completed" | "failed" | "interrupted" | string;
  events: RunEvent[];
  latest_seq: number;
  error_message?: string | null;
}

export type ThemeMode = "light" | "dark";
export type ViewName =
  | "new"
  | "chat"
  | "workspace"
  | "personalSpace"
  | "personalSpaceDetail"
  | "teamSpaces"
  | "teamSpaceChat"
  | "teamSpaceDetail"
  | "agents"
  | "skills"
  | "feedback"
  | "usage"
  | "loginWhitelist"
  | "businessMap"
  | "marketingMap"
  | "visitRecords"
  | "organization"
  | "userApproval";

export interface UsageOverview {
  call_count: number;
  active_user_count: number;
  agent_count: number;
  skill_trigger_count: number;
  plugin_trigger_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  error_count: number;
  interrupted_count: number;
  avg_duration_ms: number | null;
}

export interface UsageTimeseriesPoint {
  bucket: string;
  call_count: number;
  active_user_count: number;
  total_tokens: number;
  error_count: number;
  input_tokens: number;
  output_tokens: number;
}

export interface UsageAgentRank {
  agent_id: number | null;
  agent_name: string;
  call_count: number;
  active_user_count: number;
  total_tokens: number;
  error_count: number;
}

export interface UsageSkillRank {
  resource_name: string;
  trigger_count: number;
}

export interface UsagePluginRank {
  plugin_name: string;
  resource_name: string;
  trigger_count: number;
}

export interface UsageStatusBreakdown {
  status: "success" | "error" | "interrupted" | string;
  count: number;
}

export interface UsageTokenSummary {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  timeseries: UsageTimeseriesPoint[];
}

export interface UsageSummary {
  range: string;
  start: string;
  end: string;
  granularity: "hour" | "day" | string;
  overview: UsageOverview;
  timeseries: UsageTimeseriesPoint[];
  agents: UsageAgentRank[];
  skills: UsageSkillRank[];
  plugins: UsagePluginRank[];
  tokens: UsageTokenSummary;
  status_breakdown: UsageStatusBreakdown[];
}

/** 用户提交问题反馈后返回的创建结果 */
export interface FeedbackIssueCreated {
  id: number;
  title: string;
  description: string;
  reporter_username: string;
  created_at: string;
  attachment_count: number;
}

/** 反馈截图附件元数据 */
export interface FeedbackAttachment {
  id: number;
  filename: string;
  content_type: string;
  size: number;
  url: string;
}

/** 管理员反馈列表条目 */
export interface FeedbackIssueListItem {
  id: number;
  title: string;
  reporter_username: string;
  created_at: string;
}

/** 管理员反馈分页列表 */
export interface FeedbackIssueList {
  items: FeedbackIssueListItem[];
  total: number;
  page: number;
  page_size: number;
}

/** 管理员反馈详情 */
export interface FeedbackIssueDetail {
  id: number;
  title: string;
  description: string;
  reporter_username: string;
  created_at: string;
  attachments: FeedbackAttachment[];
}

export interface UploadItem {
  name: string;
  path: string | null;
  size: number;
  preview_path: string | null;
  agent_path: string | null;
  converted: boolean;
  conversion_task_id: number | null;
  status: "success" | "failed";
  error: string | null;
}

export interface UploadBatch {
  summary: { total: number; succeeded: number; failed: number };
  items: UploadItem[];
}

/** 个人空间上传任务,与 backend.app.schemas.UploadTaskOut 对齐 */
export interface UploadTask {
  id: number;
  target_dir: string;
  relative_path: string;
  filename: string;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number;
  size: number;
  saved_path: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface UploadTaskCreateItem {
  filename: string;
  relative_path: string;
  size: number;
}

/** 个人空间右侧统一任务列表项,task_key 用于区分上传/转换任务的同名数字 id */
export interface WorkspaceTask {
  task_key: string;
  type: "upload" | "conversion";
  id: number;
  name: string;
  path: string;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ConversionTask {
  id: number;
  source_path: string;
  source_name: string;
  status: "queued" | "running" | "succeeded" | "failed";
  error_message: string | null;
  markdown_path: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface FileNode {
  name: string;
  path: string;
  type: "file" | "dir";
  size?: number;
  mtime?: number;
  children?: FileNode[];
}

export interface AgentCommand {
  name: string;
  description: string;
  source: "personal_skill" | "skill" | "plugin";
  plugin: string | null;
}

export interface SkillMeta {
  name: string;
  description: string;
}

export interface PluginMeta {
  name: string;
  version: string;
  description: string;
  path: string;
}

export type AdminTab = "skills" | "plugins" | "categories";

// ─── 组织架构（自建三级：公司→部门→小组）──────────────────────

export type OrganizationType = "company" | "department" | "group";

/** 用户-组织关联信息 */
export interface UserOrganization {
  user_id: number;
  organization_id: number;
  username: string;
  display_name: string | null;
  position_title: string | null;
  is_primary: boolean;
}

/** 单个组织节点 */
export interface Organization {
  id: number;
  name: string;
  type: OrganizationType;
  parent_id: number | null;
  head_user_id: number | null;
  head_user_name: string | null;
  sort_order: number;
  created_at: string | null;
  updated_at: string | null;
}

/** 组织树节点（递归） */
export interface OrganizationTreeNode extends Organization {
  members: UserOrganization[];
  children: OrganizationTreeNode[];
}

/** 创建/更新组织 */
export interface OrganizationInput {
  name: string;
  type: OrganizationType;
  parent_id?: number | null;
  head_user_id?: number | null;
  sort_order?: number;
}

/** 批量导入单行 */
export interface OrganizationImportRow {
  name: string;
  type: OrganizationType;
  parent_name?: string | null;
  head_user_username?: string | null;
  position_title?: string | null;
  is_primary?: boolean;
  sort_order?: number;
}

/** 批量导入结果 */
export interface OrganizationImportResult {
  total: number;
  created: number;
  skipped: number;
  errors: string[];
}

export interface OrganizationImportResponse {
  success: boolean;
  result: OrganizationImportResult;
}

// ─── 客户与项目（M1.3）──────────────────────────────────────────

/** 客户 */
export interface Customer {
  id: number;
  name: string;
  industry: string | null;
  scale: string | null;
  region: string | null;
  description: string | null;
  created_by: number;
  created_by_name: string | null;
  visibility: "private" | "team";
  sensitivity_level: string;
  project_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface CustomerInput {
  name: string;
  industry?: string | null;
  scale?: "大型" | "中型" | "小型" | null;
  region?: string | null;
  description?: string | null;
  visibility?: "private" | "team";
  sensitivity_level?: string;
}

/** 项目 */
export type ProjectFdeStage =
  | "lead_screening"
  | "visit_preparation"
  | "onsite_validation"
  | "retrospective";
export type ProjectStatus = "active" | "paused" | "completed" | "archived";

export interface Project {
  id: number;
  customer_id: number;
  customer_name: string | null;
  name: string;
  agent_id: number | null;
  project_type: string | null;
  fde_stage: ProjectFdeStage;
  status: ProjectStatus;
  owner_id: number;
  owner_name: string | null;
  description: string | null;
  objectives: string | null;
  start_date: string | null;
  end_date: string | null;
  created_by: number;
  created_by_name: string | null;
  visibility: "private" | "team";
  sensitivity_level: string;
  member_count: number;
  /** 当前用户在该项目的角色：owner/deputy/admin/none */
  my_role: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProjectInput {
  customer_id: number;
  name: string;
  project_type?: "诊断" | "试点" | "落地" | null;
  fde_stage?: ProjectFdeStage;
  status?: ProjectStatus;
  description?: string | null;
  objectives?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  visibility?: "private" | "team";
  sensitivity_level?: string;
}

/** 项目成员 */
export interface ProjectMember {
  id: number;
  project_id: number;
  user_id: number;
  username: string;
  display_name: string | null;
  role: "owner" | "deputy";
  joined_at: string | null;
}

/** 项目-部门授权 */
export interface ProjectDepartmentAccess {
  id: number;
  project_id: number;
  organization_id: number;
  organization_name: string | null;
  granted_by: number;
  granted_by_name: string | null;
  granted_at: string | null;
}

// ─── 业务地图（M4.1 / §5.2）──────────────────────────────────
// 顶层对象字段为 snake_case（与后端 BusinessMapObjectOut 对齐），
// payload 内部为 camelCase（§5.2 规格契约，由 Skill/前端约定）。

/** 五维健康单维评分 */
export interface FiveDimScore {
  score: number; // 1-5
  desc: string;
}

/** 五维健康（5 个维度，键名含中文；保留索引签名兼容宽松数据） */
export interface FiveDimHealth {
  L5_数字意识?: FiveDimScore;
  L4_数字神经?: FiveDimScore;
  L3_数字器官?: FiveDimScore;
  L2_数字血液?: FiveDimScore;
  L1_数字骨架?: FiveDimScore;
  [key: string]: FiveDimScore | undefined;
}

/** L3 业务本体抽取（先本体后 AI） */
export interface OntologyExtraction {
  entities?: string;
  relations?: string;
  rules?: string;
  actions?: string;
}

/** 业务地图节点 payload（层级差异化，camelCase，§5.2） */
export interface BusinessMapPayload {
  // 通用
  confidenceLevel?: string; // 高 / 中 / 低
  sourceType?: string; // 搜索采集 / 用户上传 / 行业模板 / 模型知识
  sourceRef?: string[];
  evidenceIds?: string[];
  generatedByAI?: boolean;
  // L1（5 要素 + 五维健康）
  coreActivities?: string;
  capabilityChain?: string;
  itSystems?: string;
  organization?: string;
  fiveDimHealth?: FiveDimHealth;
  // L2（8 要素 + 五维健康）
  domainType?: string; // 业务域 / 职能域 / 共性技术域
  domainGoal?: string;
  valueStream?: string;
  subScenarios?: string;
  coreCapabilities?: string;
  supportITSystems?: string;
  keyOrganizations?: string;
  keyDataEntities?: string;
  disconnectionPoints?: string;
  // L3（11 要素 + 本体抽取 + 五维健康）
  businessObjective?: string;
  businessProcess?: string;
  keyActivities?: string;
  capabilityUnits?: string;
  dataFlow?: string;
  positions?: string;
  supportSystems?: string;
  painPoints?: string;
  ontologyExtraction?: OntologyExtraction;
  aiOpportunity?: string;
  // L4（9 要素）
  l3KeyActivity?: string;
  capabilityUnitName?: string;
  capabilityType?: string;
  capabilityDetail?: string;
  masteryLevel?: string;
  associatedPosition?: string;
  currentRate?: string;
  talentGap?: string;
  [key: string]: unknown;
}

export type BusinessMapLevel = "L1" | "L2" | "L3" | "L4";
export type BusinessMapType = "hypothesis" | "current";
export type BusinessMapReviewStatus =
  | "draft"
  | "pending_review"
  | "reviewed"
  | "rejected";

/** 业务地图节点（输出） */
export interface BusinessMapObject {
  id: number;
  project_id: number;
  level: BusinessMapLevel;
  name: string;
  parent_id: number | null;
  map_type: BusinessMapType;
  verification_status: string; // 未验证 / 成立 / 部分成立 / 推翻 / 待补充
  linked_hypothesis_id: number | null;
  payload: BusinessMapPayload | null;
  review_status: BusinessMapReviewStatus;
  reviewed_by: number | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  generated_by_ai: boolean;
  created_by: number;
  created_by_name: string | null;
  is_public: boolean;
  shared_with: number[] | null;
  sensitivity_level: string;
  created_at: string | null;
  updated_at: string | null;
}

/** 业务地图节点（创建/更新入参） */
export interface BusinessMapObjectInput {
  level: BusinessMapLevel;
  name: string;
  parent_id?: number | null;
  map_type?: BusinessMapType;
  verification_status?: string;
  linked_hypothesis_id?: number | null;
  payload?: BusinessMapPayload | null;
  review_status?: BusinessMapReviewStatus;
  generated_by_ai?: boolean;
  is_public?: boolean;
  shared_with?: number[] | null;
  sensitivity_level?: string;
}

/** 前置分析（项目级，一份） */
export interface PreAnalysis {
  id: number;
  project_id: number;
  industry_value_chain: string | null;
  customer_position: string | null;
  industry_trends: string | null;
  strategic_positioning: string | null;
  digitalization_drivers: string | null;
  created_by: number;
  created_by_name: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PreAnalysisInput {
  industry_value_chain?: string | null;
  customer_position?: string | null;
  industry_trends?: string | null;
  strategic_positioning?: string | null;
  digitalization_drivers?: string | null;
}

/** 业务地图版本快照 */
export interface BusinessMapVersion {
  id: number;
  project_id: number;
  version_number: number;
  snapshot_data: Record<string, unknown> | null;
  change_description: string | null;
  created_by: number;
  created_by_name: string | null;
  created_at: string | null;
}

/** 五维健康计算结果（单节点） */
export interface FiveDimHealthOut {
  object_id: number;
  five_dim_health: FiveDimHealth;
  source: "auto" | "manual" | string;
}

// ─── 营销地图（M4.2 / §5.2）──────────────────────────────────
// 顶层对象字段为 snake_case（与后端 StakeholderCardOut 等对齐），
// objective_layer / subjective_layer / behaviors / stance_change_log 内部为
// camelCase（§5.2 规格契约；compositeScore / gradeLevel 由后端按公式算回写）。

/** 角色类型（五类，§5.2） */
export type StakeholderRoleType =
  | "economic_decision_maker"
  | "technical_evaluator"
  | "user"
  | "coach_supporter"
  | "procurement_finance";

/** 关系类型（四种，§5.2 StakeholderRelation） */
export type StakeholderRelationType =
  | "reports_to"
  | "influences"
  | "collaborates"
  | "opposes";

/** 知识库分类（三种） */
export type KnowledgeCategory =
  | "role_recognition"
  | "behavior_quick_ref"
  | "onboarding_guide";

export type ReviewStatus = "draft" | "pending_review" | "reviewed" | "rejected";

/** 立场（中文枚举） */
export type StanceLevel = "支持" | "中立" | "反对" | "观望";

/** 综合评分等级（后端按 compositeScore 计算） */
export type GradeLevel = "Champion" | "倾向我方" | "中立" | "反对";

/** 决策权（中文枚举） */
export type DecisionPower =
  | "最终决策"
  | "技术把关"
  | "推荐建议"
  | "影响者"
  | "信息提供";

/** 角色卡 · 客观层（camelCase JSONB，§5.2 objectiveLayer） */
export interface StakeholderObjectiveLayer {
  education?: string;
  previousCompanies?: string;
  personality?: string;
  communicationPreference?: string;
  relationships?: string;
  historyWithUs?: string;
  historyWithCompetitor?: string;
  [key: string]: unknown;
}

/** 角色卡 · 主观层（camelCase JSONB，§5.2 subjectiveLayer） */
export interface StakeholderSubjectiveLayer {
  stance?: StanceLevel;
  explicitKPI?: string;
  personalMotivation?: string;
  attitudeToUs?: string;
  attitudeToCompetitor?: string;
  engagement?: number; // 1-10，权重 0.3
  influence?: number; // 1-10，权重 0.4
  support?: number; // 1-10，权重 0.3
  /** 综合评分 = engagement×0.3 + influence×0.4 + support×0.3（后端算回写） */
  compositeScore?: number;
  gradeLevel?: GradeLevel;
  confidence?: string; // 高 / 中 / 低
  coreConcerns?: string;
  leverage?: string;
  [key: string]: unknown;
}

/** 行为分析条目 */
export interface BehaviorEntry {
  observation?: string;
  interpretation?: string;
  suggestedAction?: string;
  [key: string]: unknown;
}

/** 态度变化记录条目（JSONB 内 from/to） */
export interface StanceChangeEntry {
  date?: string;
  from?: StanceLevel;
  to?: StanceLevel;
  reason?: string;
  [key: string]: unknown;
}

/** 角色卡（输出，对齐 StakeholderCardOut） */
export interface StakeholderCard {
  id: number;
  project_id: number;
  name: string;
  position: string | null;
  department: string | null;
  reports_to: string | null;
  contact_info: string | null;
  role_type: StakeholderRoleType | null;
  decision_power: string | null;
  objective_layer: StakeholderObjectiveLayer | null;
  subjective_layer: StakeholderSubjectiveLayer | null;
  behaviors: BehaviorEntry[] | null;
  stance_change_log: StanceChangeEntry[] | null;
  review_status: ReviewStatus;
  reviewed_by: number | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  created_by: number;
  created_by_name: string | null;
  is_public: boolean;
  shared_with: number[] | null;
  sensitivity_level: string;
  /** 产出该草稿的会话 ID（M4.4.5 待采纳徽标"跳回原对话"用） */
  source_session_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** 角色卡创建/更新入参（对齐 StakeholderCardCreate/Update） */
export interface StakeholderCardInput {
  name?: string;
  position?: string | null;
  department?: string | null;
  reports_to?: string | null;
  contact_info?: string | null;
  role_type?: StakeholderRoleType | null;
  decision_power?: string | null;
  objective_layer?: StakeholderObjectiveLayer | null;
  subjective_layer?: StakeholderSubjectiveLayer | null;
  behaviors?: BehaviorEntry[] | null;
  stance_change_log?: StanceChangeEntry[] | null;
  review_status?: ReviewStatus;
  is_public?: boolean;
  shared_with?: number[] | null;
  sensitivity_level?: string;
}

/** 角色关系（输出，对齐 StakeholderRelationOut） */
export interface StakeholderRelation {
  id: number;
  project_id: number;
  from_card_id: number;
  from_card_name: string | null;
  to_card_id: number;
  to_card_name: string | null;
  relation_type: StakeholderRelationType;
  description: string | null;
  created_by: number;
  created_at: string | null;
}

export interface StakeholderRelationInput {
  from_card_id: number;
  to_card_id: number;
  relation_type: StakeholderRelationType;
  description?: string | null;
}

/** 关系网络图（节点+边） */
export interface StakeholderGraphNode {
  id: number;
  name: string;
  role_type: StakeholderRoleType | null;
  department: string | null;
}
export interface StakeholderGraphEdge {
  id: number;
  source: number;
  target: number;
  relation_type: StakeholderRelationType;
  description: string | null;
}
export interface StakeholderGraph {
  nodes: StakeholderGraphNode[];
  edges: StakeholderGraphEdge[];
}

/** 话术（输出，对齐 TalkScriptOut） */
export interface TalkScript {
  id: number;
  project_id: number;
  stakeholder_card_id: number | null;
  stakeholder_card_name: string | null;
  role_type: StakeholderRoleType | null;
  scenario: string | null;
  content: string;
  source_customer_quote: string | null;
  is_template: boolean;
  created_by: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface TalkScriptInput {
  stakeholder_card_id?: number | null;
  role_type?: StakeholderRoleType | null;
  scenario?: string | null;
  content?: string;
  source_customer_quote?: string | null;
  is_template?: boolean;
}

/** 知识库（输出，对齐 KnowledgeBaseOut） */
export interface KnowledgeBase {
  id: number;
  project_id: number;
  category: KnowledgeCategory;
  title: string;
  content: string;
  created_by: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface KnowledgeBaseInput {
  category: KnowledgeCategory;
  title?: string;
  content?: string;
}

// ─── 采购流程时间线（M4.2.5 / §5.2）──────────────────────────

/** 采购阶段状态（四态） */
export type ProcurementStageStatus =
  | "not_started"
  | "in_progress"
  | "completed"
  | "blocked";

/** 采购阶段 key（固定五阶段通用模板） */
export type ProcurementStageKey =
  | "need_identification"
  | "solution_evaluation"
  | "vendor_screening"
  | "commercial_negotiation"
  | "contract_signing";

/** 采购单阶段（camelCase JSONB，与后端 ProcurementStageOut 对齐） */
export interface ProcurementStage {
  key: ProcurementStageKey;
  name: string;
  status: ProcurementStageStatus;
  startDate: string | null;
  endDate: string | null;
  note: string | null;
  ownerCardId: number | null;
}

/** 采购时间线（项目级单例，对齐 ProcurementTimelineOut） */
export interface ProcurementTimeline {
  id: number;
  project_id: number;
  stages: ProcurementStage[];
  created_by: number;
  created_by_name: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** 采购时间线 upsert 入参（整体替换 stages） */
export interface ProcurementTimelineInput {
  stages: ProcurementStage[];
}

/** 态度变化（POST 返回，对齐 StanceChangeOut） */
export interface StanceChangeResult {
  date: string;
  from_stance: StanceLevel;
  to_stance: StanceLevel;
  reason: string;
}

/** 拜访记录（输出，对齐 VisitRecordOut；M4.3 全量字段待补，此处含徽标所需子集） */
export interface VisitRecord {
  id: number;
  project_id: number;
  visit_date: string | null;
  visit_type: string;
  participants_our: string[] | null;
  participants_client: number[] | null;
  location: string | null;
  duration: string | null;
  summary: string | null;
  next_steps: string | null;
  key_takeaways: string[] | null;
  related_card_ids: number[] | null;
  evidence_count: number;
  verified_hypotheses: number;
  review_status: ReviewStatus;
  reviewed_by: number | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  created_by: number;
  created_by_name: string | null;
  is_public: boolean;
  shared_with: number[] | null;
  sensitivity_level: string;
  /** 产出该草稿的会话 ID（M4.4.5 待采纳徽标"跳回原对话"用） */
  source_session_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** 业务地图草稿（active，对齐 BusinessMapDraftOut 子集；M4.4.5 徽标用） */
export interface BusinessMapDraft {
  id: number;
  project_id: number;
  revision: number;
  status: string;
  source_session_id: string | null;
  created_at: string | null;
}

/** 证据源（M2.3 / §7.5 证据验证联动） */
export interface EvidenceSource {
  id: number;
  project_id: number;
  visit_record_id: number;
  evidence_type: string; // 客户原话 / 行为观察 / 角色态度信号 / 业务术语
  strength: string; // 强 / 中 / 弱
  strength_note: string | null;
  content: string;
  source_role_id: number | null;
  source_role_name: string | null;
  related_hypothesis_id: number | null;
  related_hypothesis_name: string | null;
  implied_from_stance: string | null;
  implied_to_stance: string | null;
  review_status: string;
  reviewed_by: number | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  created_by: number;
  created_by_name: string | null;
  created_at: string | null;
  updated_at: string | null;
}
