// 业务地图页面（M4.1 / §2.3 §5.2）
// 替换 V1.0 原型：改为消费真实后端 /api/projects/{id}/business-map/objects。
// 顶部项目选择器由全局 Topbar（M1.3.9/M4.4.1）驱动，本页接收 project prop。
// 本提交覆盖 M4.1.1 页面骨架 + M4.1.2 L1-L4 树形 + M4.1.3 假设视图 + M4.1.4 现状视图
// + M4.1.5 偏差池（前置分析/五维健康/节点CRUD/版本/证据见后续任务）。
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import { Card, Spinner, Tag, useToast } from "@/components/ui";
import { I } from "@/icons";
import type {
  BusinessMapObject,
  BusinessMapPayload,
  FiveDimHealth,
  Project,
} from "@/types";

// ─── 常量 ─────────────────────────────────────────────────────

type SubView = "hypothesis" | "current" | "deviation" | "preanalysis" | "health";

/** 五维健康维度展示顺序（规格 §5.2，键名含中文） */
const DIM_ORDER: { key: keyof FiveDimHealth; label: string }[] = [
  { key: "L5_数字意识", label: "数字意识" },
  { key: "L4_数字神经", label: "数字神经" },
  { key: "L3_数字器官", label: "数字器官" },
  { key: "L2_数字血液", label: "数字血液" },
  { key: "L1_数字骨架", label: "数字骨架" },
];

const LEVEL_COLOR: Record<string, string> = {
  L1: "var(--accent)",
  L2: "var(--info)",
  L3: "var(--success)",
  L4: "var(--warn)",
};

const SUBVIEWS: { key: SubView; label: string; icon: keyof typeof I }[] = [
  { key: "hypothesis", label: "假设地图", icon: "Map" },
  { key: "current", label: "现状地图", icon: "ClipboardCheck" },
  { key: "deviation", label: "偏差池", icon: "AlertTriangle" },
  { key: "preanalysis", label: "前置分析", icon: "Search" },
  { key: "health", label: "五维健康", icon: "Activity" },
];

// 已结案的验证状态（成立/部分成立=已证实；推翻=已证伪）
const VERIFIED_STATES = ["成立", "部分成立"];
const OVERTURNED_STATE = "推翻";

interface Props {
  /** 全局选中项目（Topbar ProjectSelector 驱动） */
  project: Project | null;
  /** 预留：关联证据跳转拜访记录（M4.1.10 接入） */
  onOpenVisitRecords?: (objectId?: number) => void;
}

// ─── 页面组件 ─────────────────────────────────────────────────

export default function BusinessMapPage({ project }: Props) {
  const toast = useToast();
  const [objects, setObjects] = useState<BusinessMapObject[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [subView, setSubView] = useState<SubView>("hypothesis");
  const [expandedL1, setExpandedL1] = useState<Set<number>>(new Set());
  const [expandedL2, setExpandedL2] = useState<Set<number>>(new Set());
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const projectId = project?.id ?? null;

  // 拉取业务地图对象（仅 reviewed 正式库）
  const refresh = useCallback(async () => {
    if (projectId == null) {
      setObjects([]);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const list = await api.listBusinessMapObjects(projectId);
      setObjects(list);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "加载业务地图失败";
      setError(msg);
      toast.showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // 切换项目时重置展开/选中状态
  useEffect(() => {
    setExpandedL1(new Set());
    setExpandedL2(new Set());
    setSelectedId(null);
    setSubView("hypothesis");
  }, [projectId]);

  // ─── 派生：层级分组 + 父子关系 ──────────────────────────────
  const byLevel = useMemo(() => {
    const filter = (lvl: string, list: BusinessMapObject[] = objects) =>
      list.filter((o) => o.level === lvl);
    return {
      L1: filter("L1"),
      L2: filter("L2"),
      L3: filter("L3"),
      L4: filter("L4"),
    };
  }, [objects]);

  // 当前子视图下的节点集合（假设/现状按 map_type 过滤；偏差取推翻的 current）
  const visibleObjects = useMemo(() => {
    if (subView === "hypothesis") return objects.filter((o) => o.map_type === "hypothesis");
    if (subView === "current") return objects.filter((o) => o.map_type === "current");
    return objects;
  }, [objects, subView]);

  const l1Nodes = byLevel.L1.filter((o) => visibleObjects.includes(o));
  const supportL2 = byLevel.L2.filter(
    (o) => o.parent_id == null && visibleObjects.includes(o),
  );

  const childrenOf = (parentId: number | null, level: string) =>
    visibleObjects.filter((o) => o.level === level && o.parent_id === parentId);

  const selected = useMemo(
    () => objects.find((o) => o.id === selectedId) ?? null,
    [objects, selectedId],
  );

  // ─── 派生：统计栏 ───────────────────────────────────────────
  const stats = useMemo(() => {
    const verified = objects.filter((o) => VERIFIED_STATES.includes(o.verification_status)).length;
    const overturned = objects.filter((o) => o.verification_status === OVERTURNED_STATE).length;
    const denom = objects.length || 1;
    const rate = Math.round((verified / denom) * 100);
    return {
      counts: { L1: byLevel.L1.length, L2: byLevel.L2.length, L3: byLevel.L3.length, L4: byLevel.L4.length },
      verified,
      overturned,
      rate,
      total: objects.length,
    };
  }, [objects, byLevel]);

  const toggle = (setId: React.Dispatch<React.SetStateAction<Set<number>>>, id: number) =>
    setId((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // ─── 渲染 ───────────────────────────────────────────────────

  // 未选项目：空状态引导
  if (project == null) {
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", padding: 40 }}>
        <Card style={{ padding: 40, textAlign: "center", maxWidth: 420 }}>
          <I.Map size={36} style={{ color: "var(--ink-4)", marginBottom: 12 }} />
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>
            请先选择项目
          </div>
          <div style={{ fontSize: 13, color: "var(--ink-3)", lineHeight: 1.7 }}>
            使用顶部项目选择器选择一个项目，即可查看其业务地图（假设地图 / 现状地图 / 偏差池 / 前置分析 / 五维健康）。
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* 项目上下文栏 */}
      <div
        style={{
          padding: "12px 20px",
          borderBottom: "1px solid var(--line)",
          background: "var(--bg)",
          display: "flex",
          alignItems: "center",
          gap: 16,
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <I.Map size={16} style={{ color: "var(--accent)", flexShrink: 0 }} />
          <span style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {project.name}
          </span>
          {project.customer_name && (
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>· {project.customer_name}</span>
          )}
          {project.my_role && (
            <Tag tone={project.my_role === "owner" ? "accent" : "neutral"}>
              {project.my_role === "owner" ? "负责人" : project.my_role === "deputy" ? "成员" : project.my_role}
            </Tag>
          )}
        </div>
        <div style={{ flex: 1 }} />
        {/* 层级计数 */}
        {(["L1", "L2", "L3", "L4"] as const).map((lv) => (
          <div key={lv} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: LEVEL_COLOR[lv], flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>
              {lv}: <b style={{ color: "var(--ink)" }}>{stats.counts[lv]}</b>
            </span>
          </div>
        ))}
        <span style={{ fontSize: 12, color: "var(--success)", fontWeight: 500 }}>
          ✅ 已验证 {stats.verified}/{stats.total}（{stats.rate}%）
        </span>
        {stats.overturned > 0 && (
          <span style={{ fontSize: 12, color: "var(--danger)", fontWeight: 500 }}>
            ⚠️ 推翻 {stats.overturned}
          </span>
        )}
        <button
          onClick={refresh}
          title="刷新"
          style={{
            all: "unset", cursor: "pointer", color: "var(--ink-3)",
            display: "flex", alignItems: "center", padding: 4, borderRadius: 6,
          }}
        >
          <I.Refresh size={14} />
        </button>
      </div>

      {/* 子视图 Tab */}
      <div
        style={{
          padding: "0 20px",
          borderBottom: "1px solid var(--line)",
          background: "var(--bg)",
          display: "flex",
          gap: 0,
          flexShrink: 0,
        }}
      >
        {SUBVIEWS.map((sv) => {
          const Icon = I[sv.icon];
          const badge = sv.key === "deviation" && stats.overturned > 0 ? stats.overturned : null;
          return (
            <button
              key={sv.key}
              onClick={() => setSubView(sv.key)}
              style={{
                padding: "10px 16px",
                background: "transparent",
                border: "none",
                borderBottom: subView === sv.key ? "2px solid var(--accent)" : "2px solid transparent",
                color: subView === sv.key ? "var(--accent)" : "var(--ink-2)",
                fontSize: 13,
                fontWeight: subView === sv.key ? 600 : 400,
                cursor: "pointer",
                fontFamily: "inherit",
                transition: "color 120ms, border-color 120ms",
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <Icon size={14} />
              {sv.label}
              {badge != null && (
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    color: "#FFFCF5",
                    background: "var(--danger)",
                    borderRadius: 999,
                    padding: "1px 6px",
                  }}
                >
                  {badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* 主内容 */}
      <div style={{ flex: 1, overflow: "auto", padding: 20, display: "flex", gap: 20 }}>
        {subView === "deviation" ? (
          <DeviationPool
            objects={objects}
            onSelect={(id) => {
              setSelectedId(id);
              setSubView("current");
            }}
          />
        ) : subView === "preanalysis" || subView === "health" ? (
          <PlaceholderView view={subView} />
        ) : loading ? (
          <Card style={{ flex: 1, padding: 40, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--ink-3)", fontSize: 13 }}>
              <Spinner size={16} /> 加载业务地图…
            </div>
          </Card>
        ) : error ? (
          <Card style={{ flex: 1, padding: 40, textAlign: "center", color: "var(--danger)", fontSize: 13 }}>
            加载失败：{error}
            <div style={{ marginTop: 12 }}>
              <button onClick={refresh} style={linkBtnStyle}>重试</button>
            </div>
          </Card>
        ) : visibleObjects.length === 0 ? (
          <EmptyMap view={subView} />
        ) : (
          <>
            {/* 左侧：L1-L4 树形 */}
            <Card style={{ flex: 1, padding: 16, overflow: "auto" }}>
              <div style={{ fontSize: 13 }}>
                {l1Nodes.map((l1) => (
                  <div key={l1.id} style={{ marginBottom: 4 }}>
                    <NodeRow
                      node={l1}
                      selectedId={selectedId}
                      expanded={expandedL1.has(l1.id)}
                      onToggle={() => toggle(setExpandedL1, l1.id)}
                      onSelect={() => setSelectedId(l1.id)}
                    />
                    {expandedL1.has(l1.id) && (
                      <div style={{ marginLeft: 24, borderLeft: "2px solid var(--line)", paddingLeft: 16, marginBottom: 8 }}>
                        {childrenOf(l1.id, "L2").map((l2) => (
                          <div key={l2.id} style={{ marginTop: 4 }}>
                            <NodeRow
                              node={l2}
                              selectedId={selectedId}
                              expanded={expandedL2.has(l2.id)}
                              onToggle={() => toggle(setExpandedL2, l2.id)}
                              onSelect={() => setSelectedId(l2.id)}
                            />
                            {expandedL2.has(l2.id) &&
                              childrenOf(l2.id, "L3").map((l3) => (
                                <div key={l3.id} style={{ marginLeft: 28, marginTop: 3 }}>
                                  <NodeRow node={l3} selectedId={selectedId} onSelect={() => setSelectedId(l3.id)} />
                                  {childrenOf(l3.id, "L4").map((l4) => (
                                    <div key={l4.id} style={{ marginLeft: 24, marginTop: 2 }}>
                                      <NodeRow node={l4} selectedId={selectedId} onSelect={() => setSelectedId(l4.id)} />
                                    </div>
                                  ))}
                                </div>
                              ))}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}

                {/* 横向支撑域（parent_id=null 的 L2） */}
                {supportL2.length > 0 && (
                  <div style={{ marginTop: 20, borderTop: "2px dashed var(--line)", paddingTop: 16 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 10 }}>
                      横向支撑域
                    </div>
                    {supportL2.map((l2) => (
                      <div key={l2.id} style={{ marginTop: 4 }}>
                        <NodeRow
                          node={l2}
                          selectedId={selectedId}
                          expanded={expandedL2.has(l2.id)}
                          onToggle={() => toggle(setExpandedL2, l2.id)}
                          onSelect={() => setSelectedId(l2.id)}
                        />
                        {expandedL2.has(l2.id) && (
                          <div style={{ marginLeft: 28, marginTop: 3 }}>
                            {childrenOf(l2.id, "L3").map((l3) => (
                              <div key={l3.id} style={{ marginBottom: 2 }}>
                                <NodeRow node={l3} selectedId={selectedId} onSelect={() => setSelectedId(l3.id)} />
                                {childrenOf(l3.id, "L4").map((l4) => (
                                  <div key={l4.id} style={{ marginLeft: 24, marginTop: 2 }}>
                                    <NodeRow node={l4} selectedId={selectedId} onSelect={() => setSelectedId(l4.id)} />
                                  </div>
                                ))}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Card>

            {/* 右侧：详情面板 */}
            <Card style={{ width: 360, padding: 20, flexShrink: 0, overflow: "auto" }}>
              {selected ? (
                <NodeDetail node={selected} allObjects={objects} onJump={(id) => setSelectedId(id)} />
              ) : (
                <div style={{ fontSize: 13, color: "var(--ink-3)", textAlign: "center", paddingTop: 40 }}>
                  👈 点击左侧树节点
                  <br />
                  查看详情
                </div>
              )}
            </Card>
          </>
        )}
      </div>
    </div>
  );
}

// ─── 树节点行 ─────────────────────────────────────────────────

function NodeRow({
  node,
  selectedId,
  expanded,
  onToggle,
  onSelect,
}: {
  node: BusinessMapObject;
  selectedId: number | null;
  expanded?: boolean;
  onToggle?: () => void;
  onSelect: () => void;
}) {
  const p = node.payload ?? {};
  const isSel = selectedId === node.id;
  const color = LEVEL_COLOR[node.level] ?? "var(--ink-3)";
  const hasChildren = node.level !== "L4"; // L4 为叶子；其余层级可能有子节点
  return (
    <div
      onClick={() => {
        onSelect();
        if (onToggle) onToggle();
      }}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: node.level === "L1" ? "10px 14px" : "7px 12px",
        background: isSel ? `${color}`.replace(")", "-soft)") : "transparent",
        border: `1px solid ${isSel ? color : "transparent"}`,
        borderRadius: node.level === "L1" ? 10 : 7,
        cursor: "pointer",
        transition: "background 120ms",
        marginLeft: 0,
      }}
    >
      {hasChildren && onToggle ? (
        <I.ChevronRight
          size={node.level === "L1" ? 12 : 10}
          style={{
            color: "var(--ink-4)",
            transform: expanded ? "rotate(90deg)" : "none",
            transition: "transform 160ms",
            flexShrink: 0,
          }}
        />
      ) : null}
      <span
        style={{
          padding: node.level === "L1" ? "2px 8px" : "1px 6px",
          borderRadius: 5,
          fontSize: node.level === "L1" ? 10 : 9,
          fontWeight: 700,
          background: `${color}`.replace(")", "-soft)"),
          color,
          flexShrink: 0,
        }}
      >
        {node.level}
      </span>
      <span
        style={{
          fontWeight: node.level === "L1" ? 600 : 500,
          fontSize: node.level === "L1" ? 14 : node.level === "L4" ? 11 : 12,
          flex: 1,
          minWidth: 0,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {node.name}
      </span>
      {/* 域类型（L2） */}
      {p.domainType && (
        <span style={{ fontSize: 10, color: "var(--ink-3)", padding: "1px 6px", borderRadius: 999, background: "var(--bg-3)", flexShrink: 0 }}>
          {p.domainType}
        </span>
      )}
      {/* 置信度 */}
      {p.confidenceLevel && <ConfidenceTag level={p.confidenceLevel} />}
      {/* 验证状态 */}
      {node.verification_status && node.verification_status !== "未验证" && (
        <span style={{ fontSize: 10, fontWeight: 500, color: statusColor(node.verification_status), flexShrink: 0 }}>
          {statusEmoji(node.verification_status)} {node.verification_status}
        </span>
      )}
      {/* L4 掌握程度 */}
      {p.masteryLevel && (
        <span
          style={{
            fontSize: 10,
            fontWeight: 600,
            color: p.masteryLevel.includes("缺口") || p.masteryLevel.includes("稀缺") ? "var(--danger)" : "var(--ink-2)",
            flexShrink: 0,
          }}
        >
          {p.masteryLevel}
        </span>
      )}
      {/* 现状标记 */}
      {node.map_type === "current" && <Tag tone="info">现状</Tag>}
    </div>
  );
}

// ─── 详情面板 ─────────────────────────────────────────────────

function NodeDetail({
  node,
  allObjects,
  onJump,
}: {
  node: BusinessMapObject;
  allObjects: BusinessMapObject[];
  onJump: (id: number) => void;
}) {
  const p: BusinessMapPayload = node.payload ?? {};
  const color = LEVEL_COLOR[node.level] ?? "var(--ink-3)";
  const linkedHypothesis = node.linked_hypothesis_id
    ? allObjects.find((o) => o.id === node.linked_hypothesis_id)
    : null;

  return (
    <div style={{ fontSize: 13 }}>
      {/* 标题 */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <span
          style={{
            padding: "2px 8px",
            borderRadius: 5,
            fontSize: 10,
            fontWeight: 700,
            background: `${color}`.replace(")", "-soft)"),
            color,
          }}
        >
          {node.level}
        </span>
        <span style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)" }}>{node.name}</span>
      </div>

      {/* 标签条 */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
        {p.confidenceLevel && <ConfidenceTag level={p.confidenceLevel} />}
        {p.sourceType && <Tag tone="neutral">{p.sourceType}</Tag>}
        {node.map_type === "current" && <Tag tone="info">现状地图</Tag>}
        {node.verification_status && node.verification_status !== "未验证" && (
          <Tag tone={statusTone(node.verification_status)}>{node.verification_status}</Tag>
        )}
        {p.generatedByAI && <Tag tone="accent">AI 生成</Tag>}
      </div>

      {/* 关联假设（current 节点可点击跳转） */}
      {linkedHypothesis && (
        <div style={{ marginBottom: 12, padding: 8, background: "var(--bg-2)", borderRadius: 6, fontSize: 12 }}>
          <span style={{ color: "var(--ink-3)" }}>关联假设：</span>
          <button onClick={() => onJump(linkedHypothesis.id)} style={linkBtnStyle}>
            {linkedHypothesis.name}
          </button>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {/* === L1 === */}
        {p.coreActivities && <Field label="核心业务活动" value={p.coreActivities} />}
        {p.capabilityChain && <Field label="能力链" value={p.capabilityChain} />}
        {p.itSystems && <Field label="IT 系统" value={p.itSystems} />}
        {p.organization && <Field label="组织" value={p.organization} />}

        {/* === L2 === */}
        {p.domainGoal && <Field label="域目标（SMART）" value={p.domainGoal} />}
        {p.valueStream && <Field label="价值流" value={p.valueStream} />}
        {p.subScenarios && <Field label="子场景" value={p.subScenarios} />}
        {p.coreCapabilities && <Field label="核心能力" value={p.coreCapabilities} />}
        {p.supportITSystems && <Field label="支撑 IT 系统" value={p.supportITSystems} />}
        {p.keyOrganizations && <Field label="关键组织/岗位" value={p.keyOrganizations} />}
        {p.keyDataEntities && <Field label="关键数据实体" value={p.keyDataEntities} />}
        {p.disconnectionPoints && <Callout label="主要脱节点" value={p.disconnectionPoints} tone="danger" />}

        {/* === L3 === */}
        {p.businessObjective && <Field label="业务目标（SMART）" value={p.businessObjective} />}
        {p.businessProcess && <Field label="业务流程" value={p.businessProcess} />}
        {p.keyActivities && <Field label="关键活动" value={p.keyActivities} />}
        {p.capabilityUnits && <Field label="能力单元" value={p.capabilityUnits} highlight />}
        {p.dataFlow && <Field label="数据流" value={p.dataFlow} />}
        {p.positions && <Field label="岗位" value={p.positions} />}
        {p.supportSystems && <Field label="支撑系统" value={p.supportSystems} />}
        {p.painPoints && <Callout label="痛点" value={p.painPoints} tone="danger" />}
        {p.ontologyExtraction && <OntologyBlock ont={p.ontologyExtraction} />}
        {p.aiOpportunity && <Field label="AI 机会点" value={p.aiOpportunity} highlight />}

        {/* === L4 === */}
        {p.l3KeyActivity && <Field label="关联 L3 关键活动" value={p.l3KeyActivity} />}
        {p.capabilityUnitName && <Field label="能力单元名称" value={p.capabilityUnitName} highlight />}
        {p.capabilityType && <Field label="能力类型" value={p.capabilityType} />}
        {p.capabilityDetail && <Field label="能力详细描述" value={p.capabilityDetail} />}
        {p.masteryLevel && (
          <Field
            label="掌握程度要求"
            value={p.masteryLevel}
            highlight={p.masteryLevel.includes("缺口") || p.masteryLevel.includes("稀缺")}
          />
        )}
        {p.associatedPosition && <Field label="关联岗位" value={p.associatedPosition} />}
        {p.currentRate && <Field label="当前能力达标率" value={p.currentRate} />}
        {p.talentGap && <Callout label="人才差距与建议" value={p.talentGap} tone="warn" />}

        {/* 五维健康（L1/L2/L3 通用） */}
        {p.fiveDimHealth && (
          <div style={{ marginTop: 8, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            <FiveDimRadar health={p.fiveDimHealth} />
          </div>
        )}
      </div>
    </div>
  );
}

// ─── 偏差池 ───────────────────────────────────────────────────

function DeviationPool({
  objects,
  onSelect,
}: {
  objects: BusinessMapObject[];
  onSelect: (id: number) => void;
}) {
  // 推翻的 current 节点 = 偏差项；关联其假设节点做对比
  const deviations = objects.filter((o) => o.verification_status === OVERTURNED_STATE);
  if (deviations.length === 0) {
    return (
      <Card style={{ flex: 1, padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
        <I.CircleCheck size={32} style={{ color: "var(--success)", marginBottom: 10 }} />
        <div style={{ fontWeight: 600, color: "var(--ink)", marginBottom: 4 }}>暂无偏差</div>
        目前没有验证状态为「推翻」的节点——假设与现状基本吻合。
      </Card>
    );
  }
  return (
    <Card style={{ flex: 1, padding: 16, overflow: "auto" }}>
      <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 12 }}>
        以下节点假设与现状存在显著偏差（验证状态=推翻），需重点关注：
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {deviations.map((d) => {
          const hypo = d.linked_hypothesis_id
            ? objects.find((o) => o.id === d.linked_hypothesis_id)
            : null;
          return (
            <div
              key={d.id}
              style={{
                padding: 14,
                background: "var(--danger-soft)",
                border: "1px solid var(--danger)",
                borderRadius: 10,
                fontSize: 13,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                <div style={{ fontWeight: 600, color: "var(--danger)", fontSize: 14 }}>
                  {d.name}（{d.level}）
                </div>
                <button onClick={() => onSelect(d.id)} style={linkBtnStyle}>
                  查看节点 →
                </button>
              </div>
              {hypo && (
                <div style={{ marginBottom: 6 }}>
                  <span style={{ fontWeight: 500, color: "var(--ink-2)" }}>📐 假设：</span>
                  <span style={{ color: "var(--ink-2)" }}>{hypo.name}</span>
                  {hypo.payload?.domainGoal && (
                    <span style={{ color: "var(--ink-3)" }}> — {hypo.payload.domainGoal}</span>
                  )}
                </div>
              )}
              <div style={{ marginBottom: 6 }}>
                <span style={{ fontWeight: 500, color: "var(--ink)" }}>🔍 现状：</span>
                <span style={{ color: "var(--ink)" }}>
                  {d.payload?.painPoints || d.payload?.disconnectionPoints || "现状与假设不符，详见节点详情"}
                </span>
              </div>
              {d.payload?.aiOpportunity && (
                <div style={{ borderTop: "1px solid var(--danger-soft)", paddingTop: 8, fontSize: 12, color: "var(--ink-2)" }}>
                  <span style={{ fontWeight: 500 }}>📌 影响：</span>
                  {d.payload.aiOpportunity}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// ─── 五维健康雷达（条形） ──────────────────────────────────────

function FiveDimRadar({ health }: { health: FiveDimHealth }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 4 }}>
        五维健康观测
      </div>
      {DIM_ORDER.map((d) => {
        const item = health[d.key];
        if (!item) return null;
        const score = typeof item.score === "number" ? item.score : 0;
        return (
          <div key={d.key} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-2)", width: 56, flexShrink: 0 }}>{d.label}</span>
            <div style={{ flex: 1, height: 6, background: "var(--bg-3)", borderRadius: 3, overflow: "hidden" }}>
              <div
                style={{
                  width: `${(score / 5) * 100}%`,
                  height: "100%",
                  background: score <= 2 ? "var(--danger)" : score === 3 ? "var(--warn)" : "var(--success)",
                  borderRadius: 3,
                  transition: "width 400ms",
                }}
              />
            </div>
            <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ink)", width: 24, textAlign: "right" }}>
              {score}/5
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ─── L3 本体抽取块 ────────────────────────────────────────────

function OntologyBlock({ ont }: { ont: NonNullable<BusinessMapPayload["ontologyExtraction"]> }) {
  return (
    <div style={{ marginTop: 8, border: "1px solid var(--accent)", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "#FFFCF5", background: "var(--accent)", padding: "6px 10px" }}>
        🧠 业务本体抽取（先本体后 AI）
      </div>
      <div style={{ padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
        {[
          { label: "实体 (Entities)", value: ont.entities, color: "var(--info)" },
          { label: "关系 (Relations)", value: ont.relations, color: "var(--success)" },
          { label: "规则 (Rules)", value: ont.rules, color: "var(--warn)" },
          { label: "动作 (Actions)", value: ont.actions, color: "var(--danger)" },
        ].map((row) =>
          row.value ? (
            <div key={row.label}>
              <div style={{ fontSize: 10, fontWeight: 600, color: row.color }}>{row.label}</div>
              <div style={{ fontSize: 11, color: "var(--ink-2)", lineHeight: 1.5 }}>{row.value}</div>
            </div>
          ) : null,
        )}
      </div>
    </div>
  );
}

// ─── 占位视图（前置分析 / 五维健康 — 后续任务实现） ────────────

function PlaceholderView({ view }: { view: "preanalysis" | "health" }) {
  const meta =
    view === "preanalysis"
      ? { title: "前置分析", task: "M4.1.6", desc: "项目级产业环境与战略定位分析（行业价值链 / 客户地位 / 行业趋势 / 战略定位 / 数字化驱动力），含查看与编辑。" }
      : { title: "五维健康", task: "M4.1.7", desc: "L1 雷达总览 + L2/L3 逐域评分表，支持重新计算与手动覆盖。" };
  return (
    <Card style={{ flex: 1, padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
      <I.Sparkles size={32} style={{ color: "var(--accent)", marginBottom: 10 }} />
      <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>{meta.title}视图</div>
      <div style={{ maxWidth: 420, margin: "0 auto", lineHeight: 1.7 }}>
        {meta.desc}
      </div>
      <div style={{ marginTop: 12, fontSize: 12, color: "var(--ink-4)" }}>
        将在 {meta.task} 实现
      </div>
    </Card>
  );
}

// ─── 空地图 ───────────────────────────────────────────────────

function EmptyMap({ view }: { view: "hypothesis" | "current" }) {
  const isCurrent = view === "current";
  return (
    <Card style={{ flex: 1, padding: 40, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
      <I.Map size={32} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
      <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)", marginBottom: 6 }}>
        {isCurrent ? "尚未生成现状地图" : "尚未生成假设地图"}
      </div>
      <div style={{ maxWidth: 380, margin: "0 auto", lineHeight: 1.7 }}>
        {isCurrent
          ? "前往「对话」页，对项目 Agent 说「验证假设」或使用 WF10 chip，AI 会基于拜访证据生成现状地图草稿，采纳后此处可见。"
          : "前往「对话」页，对项目 Agent 说「生成假设地图」或使用 WF07 chip，AI 会产出业务地图草稿，采纳后此处可见。"}
      </div>
    </Card>
  );
}

// ─── 通用小组件 ───────────────────────────────────────────────

function Field({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, color: highlight ? "var(--accent)" : "var(--ink-3)", marginBottom: 3 }}>
        {label}
      </div>
      <div style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.55 }}>{value}</div>
    </div>
  );
}

function Callout({ label, value, tone }: { label: string; value: string; tone: "danger" | "warn" }) {
  const color = tone === "danger" ? "var(--danger)" : "var(--warn)";
  const bg = tone === "danger" ? "var(--danger-soft)" : "var(--warn-soft)";
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, color, marginBottom: 4, marginTop: 4 }}>{label}</div>
      <div style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.6, background: bg, padding: 8, borderRadius: 6 }}>
        {value}
      </div>
    </div>
  );
}

function ConfidenceTag({ level }: { level: string }) {
  if (level === "高") return <Tag tone="success">高置信</Tag>;
  if (level === "中") return <Tag tone="warn">中置信</Tag>;
  return <Tag tone="neutral">低置信</Tag>;
}

// ─── 工具函数 ─────────────────────────────────────────────────

function statusColor(s: string): string {
  if (s === "成立") return "var(--success)";
  if (s === "部分成立") return "var(--warn)";
  if (s === OVERTURNED_STATE) return "var(--danger)";
  return "var(--ink-3)";
}

function statusTone(s: string): "success" | "warn" | "danger" | "neutral" {
  if (s === "成立") return "success";
  if (s === "部分成立") return "warn";
  if (s === OVERTURNED_STATE) return "danger";
  return "neutral";
}

function statusEmoji(s: string): string {
  if (s === "成立") return "✅";
  if (s === "部分成立") return "⚠️";
  if (s === OVERTURNED_STATE) return "❌";
  return "";
}

const linkBtnStyle: React.CSSProperties = {
  all: "unset",
  cursor: "pointer",
  color: "var(--accent)",
  fontSize: 12,
  fontWeight: 500,
};
