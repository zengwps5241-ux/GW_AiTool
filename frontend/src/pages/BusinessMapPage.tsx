// 业务地图页面（M4.1 / §2.3 §5.2）
// 替换 V1.0 原型：改为消费真实后端 /api/projects/{id}/business-map/objects。
// 顶部项目选择器由全局 Topbar（M1.3.9/M4.4.1）驱动，本页接收 project prop。
// 本提交覆盖 M4.1.1 页面骨架 + M4.1.2 L1-L4 树形 + M4.1.3 假设视图 + M4.1.4 现状视图
// + M4.1.5 偏差池（前置分析/五维健康/节点CRUD/版本/证据见后续任务）。
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import { Btn, Card, ConfirmDialog, Input, Spinner, Tag, TextArea, useToast } from "@/components/ui";
import { VisibilityControls } from "@/components/VisibilityControls";
import { I } from "@/icons";
import type {
  BusinessMapLevel,
  BusinessMapObject,
  BusinessMapPayload,
  BusinessMapType,
  BusinessMapVersion,
  EvidenceSource,
  FiveDimHealth,
  PreAnalysis,
  PreAnalysisInput,
  Project,
  VersionDiff,
  VersionDiffChangedItem,
  VersionDiffItem,
} from "@/types";

// ─── 常量 ─────────────────────────────────────────────────────

type SubView = "hypothesis" | "current" | "deviation" | "preanalysis" | "health" | "version";

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
  { key: "version", label: "版本管理", icon: "Database" },
];

// 已结案的验证状态（成立/部分成立=已证实；推翻=已证伪）
const VERIFIED_STATES = ["成立", "部分成立"];
const OVERTURNED_STATE = "推翻";

interface Props {
  /** 全局选中项目（Topbar ProjectSelector 驱动） */
  project: Project | null;
  /** 预留：关联证据跳转拜访记录（M4.1.10 接入） */
  onOpenVisitRecords?: (objectId?: number) => void;
  /** 跨页聚焦目标节点 id（M4.3.7 证据→业务地图），一次性消费 */
  focusObjectId?: number | null;
  /** 聚焦应用完毕回调（清空 App.focusTarget，防重复触发） */
  onFocusConsumed?: () => void;
}

// ─── 页面组件 ─────────────────────────────────────────────────

export default function BusinessMapPage({ project, onOpenVisitRecords, focusObjectId, onFocusConsumed }: Props) {
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

  // 跨页聚焦（M4.3.7 证据→业务地图节点）：选中目标 + 切对应子视图 + 展开祖先链使节点在树中可见
  // objects 为空时数据尚未加载，等待；加载后无论是否命中均一次性消费 focusObjectId。
  useEffect(() => {
    if (focusObjectId == null || objects.length === 0) return;
    const obj = objects.find((o) => o.id === focusObjectId);
    if (obj) {
      setSelectedId(obj.id);
      setSubView(obj.map_type === "current" ? "current" : "hypothesis");
      // 沿 parent_id 上溯展开 L1/L2 祖先，让目标节点在左侧树可视
      let parentId: number | null = obj.parent_id;
      while (parentId != null) {
        const parent = objects.find((o) => o.id === parentId);
        if (!parent) break;
        if (parent.level === "L1") setExpandedL1((s) => new Set(s).add(parent.id));
        else if (parent.level === "L2") setExpandedL2((s) => new Set(s).add(parent.id));
        parentId = parent.parent_id;
      }
    }
    onFocusConsumed?.();
    // 仅依赖 focusObjectId 与 objects；onFocusConsumed 为一次性内联回调，不计入依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusObjectId, objects]);

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

  // 节点 CRUD（M4.1.8）：编辑/新增弹窗 + 删除确认
  const [nodeEdit, setNodeEdit] = useState<{ mode: "create" | "edit"; node?: BusinessMapObject } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<BusinessMapObject | null>(null);

  const confirmDelete = async () => {
    if (!deleteTarget || projectId == null) return;
    const target = deleteTarget;
    setDeleteTarget(null);
    try {
      await api.deleteBusinessMapObject(projectId, target.id);
      if (selectedId === target.id) setSelectedId(null);
      toast.showToast("节点已删除", "success");
      refresh();
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "删除失败", "error");
    }
  };

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
                    color: "var(--on-accent)",
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
        ) : subView === "preanalysis" ? (
          <PreAnalysisView projectId={project.id} />
        ) : subView === "health" ? (
          <HealthView
            objects={objects}
            projectId={project.id}
            onChanged={refresh}
            onJump={(node) => {
              setSelectedId(node.id);
              setSubView(node.map_type === "current" ? "current" : "hypothesis");
            }}
          />
        ) : subView === "version" ? (
          <VersionView
            projectId={project.id}
            canRollback={project.my_role === "owner" || project.my_role === "admin"}
            onChanged={refresh}
          />
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
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-2)" }}>
                  {subView === "current" ? "现状地图" : "假设地图"}
                </div>
                <Btn size="sm" variant="ghost" icon={<I.Plus size={13} />} onClick={() => setNodeEdit({ mode: "create" })}>
                  新增节点
                </Btn>
              </div>
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
                <NodeDetail
                  node={selected}
                  allObjects={objects}
                  onJump={(id) => setSelectedId(id)}
                  onEdit={(node) => setNodeEdit({ mode: "edit", node })}
                  onDelete={(node) => setDeleteTarget(node)}
                  onOpenVisitRecords={onOpenVisitRecords}
                />
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

      {/* 节点 CRUD 弹窗 / 删除确认（M4.1.8） */}
      {nodeEdit && (
        <NodeEditModal
          mode={nodeEdit.mode}
          node={nodeEdit.node}
          allObjects={objects}
          projectId={project.id}
          onClose={() => setNodeEdit(null)}
          onSaved={(id) => {
            setNodeEdit(null);
            if (id) setSelectedId(id);
            refresh();
          }}
        />
      )}
      <ConfirmDialog
        open={deleteTarget != null}
        title="删除节点"
        message={
          deleteTarget
            ? `确认删除节点「${deleteTarget.name}」（${deleteTarget.level}）？该操作不可撤销，子节点需另行处理。`
            : ""
        }
        confirmText="删除"
        variant="danger"
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

// ─── 版本管理（M4.1.9：列表 + 查看快照 + 回滚） ───────────────

interface SnapshotObjectSpec {
  level?: string;
  name?: string;
  map_type?: string;
  parent_id?: number | null;
  verification_status?: string;
}

function VersionView({
  projectId,
  canRollback,
  onChanged,
}: {
  projectId: number;
  canRollback: boolean;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [versions, setVersions] = useState<BusinessMapVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewing, setViewing] = useState<BusinessMapVersion | null>(null);
  const [diffing, setDiffing] = useState<BusinessMapVersion | null>(null);
  const [rollbackTarget, setRollbackTarget] = useState<BusinessMapVersion | null>(null);
  const [rolling, setRolling] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setVersions(await api.listBusinessMapVersions(projectId));
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "加载版本失败", "error");
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const doRollback = async () => {
    if (!rollbackTarget) return;
    const target = rollbackTarget;
    setRollbackTarget(null);
    setRolling(true);
    try {
      await api.rollbackBusinessMapVersion(projectId, target.id);
      toast.showToast(`已回滚到版本 #${target.version_number}`, "success");
      onChanged();
      refresh();
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "回滚失败（仅负责人/管理员可操作）", "error");
    } finally {
      setRolling(false);
    }
  };

  if (loading) {
    return (
      <Card style={{ flex: 1, padding: 40, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--ink-3)", fontSize: 13 }}>
          <Spinner size={16} /> 加载版本…
        </div>
      </Card>
    );
  }

  return (
    <>
      <Card style={{ flex: 1, padding: 20, overflow: "auto" }}>
        <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)", marginBottom: 4 }}>版本管理</div>
        <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 16 }}>
          每次采纳业务地图草稿会自动生成版本快照（M2.1.8）；回滚仅替换 reviewed 正式数据，不影响草稿。
        </div>
        {versions.length === 0 ? (
          <div style={{ padding: 30, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
            <I.Database size={28} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
            暂无版本快照。在对话中生成业务地图草稿（WF07）并采纳后，将自动生成首个版本。
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {versions.map((v) => {
              const objs = (v.snapshot_data?.objects as SnapshotObjectSpec[] | undefined) ?? [];
              return (
                <div key={v.id} style={{ padding: 14, border: "1px solid var(--line)", borderRadius: 10, background: "var(--surface)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                    <span style={{ padding: "2px 8px", borderRadius: 5, fontSize: 11, fontWeight: 700, background: "var(--accent-soft)", color: "var(--accent)" }}>
                      v{v.version_number}
                    </span>
                    <span style={{ fontSize: 13, fontWeight: 500, color: "var(--ink-2)", flex: 1 }}>{v.change_description}</span>
                    <span style={{ fontSize: 11, color: "var(--ink-4)" }}>
                      {v.created_at?.slice(0, 16).replace("T", " ")}
                      {v.created_by_name ? ` · ${v.created_by_name}` : ""}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: 11, color: "var(--ink-3)" }}>
                      {objs.length > 0 ? `含 ${objs.length} 个对象（L1:${objs.filter((o) => o.level === "L1").length} / L2:${objs.filter((o) => o.level === "L2").length} / L3:${objs.filter((o) => o.level === "L3").length} / L4:${objs.filter((o) => o.level === "L4").length}）` : "空快照"}
                    </span>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button onClick={() => setViewing(v)} style={linkBtnStyle}>查看快照</button>
                      <button onClick={() => setDiffing(v)} style={{ ...linkBtnStyle, color: "var(--info)" }}>
                        对比当前
                      </button>
                      {canRollback && (
                        <button
                          onClick={() => setRollbackTarget(v)}
                          disabled={rolling}
                          style={{ ...linkBtnStyle, color: "var(--warn)" }}
                        >
                          回滚到此版本
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <Card style={{ width: 300, padding: 20, flexShrink: 0, overflow: "auto" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 12 }}>
          📖 版本说明
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, fontSize: 12, color: "var(--ink-2)", lineHeight: 1.6 }}>
          <div><b>版本生成</b>：每次采纳业务地图草稿自动生成一个版本快照（含当时全部 reviewed 对象）。</div>
          <div><b>回滚</b>：把当前正式数据替换为目标版本内容；回滚前会先留存一份审计快照（可再次回滚回来）。仅<b>负责人/管理员</b>可操作。</div>
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12, color: "var(--ink-3)" }}>
            回滚仅影响 reviewed 正式对象，草稿区与 pending_review 数据不受影响（§7.4）。
          </div>
          {!canRollback && (
            <div style={{ padding: 8, background: "var(--warn-soft)", borderRadius: 6, fontSize: 11, color: "var(--warn)" }}>
              当前角色无回滚权限（需负责人或管理员）。
            </div>
          )}
        </div>
      </Card>

      {viewing && <SnapshotModal version={viewing} onClose={() => setViewing(null)} />}
      {diffing && (
        <DiffModal version={diffing} projectId={projectId} onClose={() => setDiffing(null)} />
      )}
      <ConfirmDialog
        open={rollbackTarget != null}
        title="回滚版本"
        message={rollbackTarget ? `确认回滚到版本 #${rollbackTarget.version_number}？当前正式数据将被替换（会先留存审计快照）。` : ""}
        confirmText="确认回滚"
        variant="danger"
        onConfirm={doRollback}
        onCancel={() => setRollbackTarget(null)}
      />
    </>
  );
}

/** 历史版本快照查看弹窗 */
function SnapshotModal({ version, onClose }: { version: BusinessMapVersion; onClose: () => void }) {
  const objs = (version.snapshot_data?.objects as SnapshotObjectSpec[] | undefined) ?? [];
  const grouped: Record<string, SnapshotObjectSpec[]> = { L1: [], L2: [], L3: [], L4: [] };
  for (const o of objs) {
    const lv = o.level && grouped[o.level] ? o.level : "L1";
    grouped[lv].push(o);
  }
  return (
    <div onClick={onClose} style={modalOverlayStyle}>
      <div onClick={(e) => e.stopPropagation()} style={{ ...modalCardStyle, width: 520, maxHeight: "80vh", overflow: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>
            版本 #{version.version_number} 快照
            <span style={{ fontSize: 12, color: "var(--ink-3)", fontWeight: 400, marginLeft: 8 }}>
              {version.created_at?.slice(0, 16).replace("T", " ")}
            </span>
          </div>
          <button onClick={onClose} style={{ all: "unset", cursor: "pointer", color: "var(--ink-3)" }}>
            <I.X size={16} />
          </button>
        </div>
        <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 12 }}>{version.change_description}</div>
        {objs.length === 0 ? (
          <div style={{ color: "var(--ink-3)", fontSize: 13, textAlign: "center", padding: 20 }}>该版本为空快照。</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {LEVELS.map((lv) =>
              grouped[lv].length > 0 ? (
                <div key={lv}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: LEVEL_COLOR[lv], marginBottom: 6 }}>{lv}（{grouped[lv].length}）</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {grouped[lv].map((o, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--ink-2)" }}>
                        <span style={{ flex: 1 }}>{o.name || "未命名"}</span>
                        {o.map_type === "current" && <Tag tone="info">现状</Tag>}
                        {o.verification_status && o.verification_status !== "未验证" && (
                          <span style={{ fontSize: 10, color: statusColor(o.verification_status) }}>{o.verification_status}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null,
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * 版本对比弹窗（M5.3.2 前端）：拉取 GET .../versions/{vid}/diff，
 * 渲染 added（绿）/ removed（红）/ changed（黄，显示 snapshot→current）。
 * 对比仅看 map_type / verification_status（§7.4），payload 五维健康等派生数据不纳入噪声。
 */
function DiffModal({
  version,
  projectId,
  onClose,
}: {
  version: BusinessMapVersion;
  projectId: number;
  onClose: () => void;
}) {
  const toast = useToast();
  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 挂载即拉取 diff（version.id/projectId 不变）
  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .diffBusinessMapVersion(projectId, version.id)
      .then((d) => {
        if (alive) setDiff(d);
      })
      .catch((e) => {
        if (!alive) return;
        const msg = e instanceof Error ? e.message : "加载对比失败";
        setError(msg);
        toast.showToast(msg, "error");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, version.id]);

  const totalChanges = diff ? diff.added.length + diff.removed.length + diff.changed.length : 0;

  return (
    <div onClick={onClose} style={modalOverlayStyle}>
      <div onClick={(e) => e.stopPropagation()} style={{ ...modalCardStyle, width: 560, maxHeight: "80vh", overflow: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>
            版本 #{version.version_number} 对比当前
            <span style={{ fontSize: 12, color: "var(--ink-3)", fontWeight: 400, marginLeft: 8 }}>
              {version.created_at?.slice(0, 16).replace("T", " ")}
            </span>
          </div>
          <button onClick={onClose} style={{ all: "unset", cursor: "pointer", color: "var(--ink-3)" }}>
            <I.X size={16} />
          </button>
        </div>
        <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 14 }}>{version.change_description}</div>

        {loading ? (
          <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--ink-3)", fontSize: 13, padding: 28, justifyContent: "center" }}>
            <Spinner size={16} /> 计算差异…
          </div>
        ) : error ? (
          <div style={{ color: "var(--danger)", fontSize: 13, textAlign: "center", padding: 20 }}>加载失败：{error}</div>
        ) : diff ? (
          <>
            {/* 概览统计 */}
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              <DiffStat label="快照对象" value={diff.snapshot_count} tone="neutral" />
              <DiffStat label="当前对象" value={diff.current_count} tone="neutral" />
              <DiffStat label="新增" value={diff.added.length} tone="success" />
              <DiffStat label="删除" value={diff.removed.length} tone="danger" />
              <DiffStat label="变更" value={diff.changed.length} tone="warn" />
            </div>

            {totalChanges === 0 ? (
              <div style={{ padding: 28, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
                <I.CircleCheck size={28} style={{ color: "var(--success)", marginBottom: 10 }} />
                <div>该版本快照与当前数据完全一致，无差异。</div>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {diff.added.length > 0 && (
                  <DiffSection title="新增（当前有 / 快照无）" tone="success" items={diff.added} />
                )}
                {diff.removed.length > 0 && (
                  <DiffSection title="删除（快照有 / 当前无）" tone="danger" items={diff.removed} />
                )}
                {diff.changed.length > 0 && (
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "var(--warn)", marginBottom: 6 }}>
                      变更（字段变化） · {diff.changed.length}
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {diff.changed.map((c, i) => (
                        <DiffChangedRow key={i} item={c} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        ) : null}

        <div style={{ borderTop: "1px solid var(--line)", marginTop: 16, paddingTop: 10, fontSize: 11, color: "var(--ink-4)" }}>
          对比仅看 map_type / verification_status 字段（§7.4），payload 内五维健康等派生数据不纳入噪声。
        </div>
      </div>
    </div>
  );
}

/** diff 概览统计块 */
function DiffStat({ label, value, tone }: { label: string; value: number; tone: "neutral" | "success" | "danger" | "warn" }) {
  const color =
    tone === "success" ? "var(--success)" : tone === "danger" ? "var(--danger)" : tone === "warn" ? "var(--warn)" : "var(--ink-2)";
  return (
    <div style={{ flex: 1, padding: "8px 6px", background: "var(--bg-2)", borderRadius: 8, textAlign: "center" }}>
      <div style={{ fontSize: 18, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 2 }}>{label}</div>
    </div>
  );
}

/** diff 新增/删除分组 */
function DiffSection({ title, tone, items }: { title: string; tone: "success" | "danger"; items: VersionDiffItem[] }) {
  const color = tone === "success" ? "var(--success)" : "var(--danger)";
  const bg = tone === "success" ? "var(--success-soft)" : "var(--danger-soft)";
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 700, color, marginBottom: 6 }}>{title} · {items.length}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {items.map((it, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, padding: "5px 8px", background: bg, borderRadius: 6 }}>
            {it.level && (
              <span style={{ fontSize: 10, fontWeight: 700, color: LEVEL_COLOR[it.level] ?? color, minWidth: 22 }}>{it.level}</span>
            )}
            <span style={{ flex: 1, color: "var(--ink-2)" }}>{it.name || "未命名"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** diff 字段变更行（snapshot → current） */
function DiffChangedRow({ item }: { item: VersionDiffChangedItem }) {
  const fieldLabel = item.field === "map_type" ? "地图类型" : item.field === "verification_status" ? "验证状态" : item.field;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, padding: "6px 8px", background: "var(--warn-soft)", borderRadius: 6, flexWrap: "wrap" }}>
      {item.level && (
        <span style={{ fontSize: 10, fontWeight: 700, color: LEVEL_COLOR[item.level] ?? "var(--warn)", minWidth: 22 }}>{item.level}</span>
      )}
      <span style={{ fontWeight: 500, color: "var(--ink-2)" }}>{item.name || "未命名"}</span>
      <span style={{ fontSize: 10, color: "var(--ink-4)" }}>{fieldLabel}：</span>
      <span style={{ fontSize: 11, padding: "1px 6px", borderRadius: 4, background: "var(--bg-3)", color: "var(--ink-3)" }}>
        {fmtVal(item.snapshot)}
      </span>
      <I.ChevronRight size={11} style={{ color: "var(--ink-4)" }} />
      <span style={{ fontSize: 11, padding: "1px 6px", borderRadius: 4, background: "var(--surface)", color: "var(--warn)", fontWeight: 600, border: "1px solid var(--warn)" }}>
        {fmtVal(item.current)}
      </span>
    </div>
  );
}

/** diff 值友好显示 */
function fmtVal(v: unknown): string {
  if (v == null || v === "") return "—";
  return String(v);
}

// ─── 节点新增/编辑弹窗（M4.1.8） ──────────────────────────────

const LEVELS: BusinessMapLevel[] = ["L1", "L2", "L3", "L4"];
const PARENT_LEVEL: Record<BusinessMapLevel, BusinessMapLevel | undefined> = {
  L1: undefined,
  L2: "L1",
  L3: "L2",
  L4: "L3",
};
const VERIFICATION_STATUSES = ["未验证", "成立", "部分成立", "推翻", "待补充"];

const selectStyle: React.CSSProperties = {
  width: "100%",
  height: 34,
  fontSize: 13,
  padding: "0 8px",
  borderRadius: 8,
  border: "1px solid var(--line)",
  background: "var(--bg)",
  color: "var(--ink)",
};

function NodeEditModal({
  mode,
  node,
  allObjects,
  projectId,
  onClose,
  onSaved,
}: {
  mode: "create" | "edit";
  node?: BusinessMapObject;
  allObjects: BusinessMapObject[];
  projectId: number;
  onClose: () => void;
  onSaved: (id?: number) => void;
}) {
  const toast = useToast();
  const isEdit = mode === "edit";
  const [level, setLevel] = useState<BusinessMapLevel>(node?.level ?? "L1");
  const [name, setName] = useState(node?.name ?? "");
  const [parentId, setParentId] = useState<number | null>(node?.parent_id ?? null);
  const [mapType, setMapType] = useState<BusinessMapType>(node?.map_type ?? "hypothesis");
  const [verificationStatus, setVerificationStatus] = useState(node?.verification_status ?? "未验证");
  const [linkedHypothesisId, setLinkedHypothesisId] = useState<number | null>(node?.linked_hypothesis_id ?? null);
  const [confidence, setConfidence] = useState(node?.payload?.confidenceLevel ?? "");
  const [source, setSource] = useState(node?.payload?.sourceType ?? "");
  const [payloadJson, setPayloadJson] = useState("");
  // 跨项目公开（M5.5.3，§5.x / §6.3）
  const [isPublic, setIsPublic] = useState<boolean>(node?.is_public ?? false);
  const [sharedWith, setSharedWith] = useState<number[]>(node?.shared_with ?? []);
  const [saving, setSaving] = useState(false);

  const parentLevel = PARENT_LEVEL[level];
  const parentOptions = parentLevel
    ? allObjects.filter((o) => o.level === parentLevel)
    : [];
  const hypothesisOptions = allObjects.filter((o) => o.map_type === "hypothesis" && o.level === level);

  const save = async () => {
    if (!name.trim()) {
      toast.showToast("请填写节点名称", "error");
      return;
    }
    // 组装 payload：高级 JSON 优先；否则合并通用字段
    let payload: BusinessMapPayload;
    if (payloadJson.trim()) {
      try {
        payload = JSON.parse(payloadJson);
      } catch {
        toast.showToast("payload JSON 格式错误", "error");
        return;
      }
    } else {
      payload = {
        ...(isEdit ? (node?.payload ?? {}) : {}),
        ...(confidence ? { confidenceLevel: confidence } : {}),
        ...(source ? { sourceType: source } : {}),
      };
    }
    setSaving(true);
    try {
      if (isEdit && node) {
        await api.updateBusinessMapObject(projectId, node.id, {
          name: name.trim(),
          parent_id: parentId,
          map_type: mapType,
          verification_status: verificationStatus,
          linked_hypothesis_id: mapType === "current" ? linkedHypothesisId : null,
          payload,
          is_public: isPublic,
          shared_with: sharedWith,
        });
        toast.showToast("节点已更新", "success");
        onSaved(node.id);
      } else {
        const created = await api.createBusinessMapObject(projectId, {
          level,
          name: name.trim(),
          parent_id: parentId,
          map_type: mapType,
          verification_status: verificationStatus,
          linked_hypothesis_id: mapType === "current" ? linkedHypothesisId : null,
          payload,
          review_status: "reviewed", // 手动新增直接进正式库（§7.3）
          generated_by_ai: false,
          is_public: isPublic,
          shared_with: sharedWith,
        });
        toast.showToast("节点已新增", "success");
        onSaved(created.id);
      }
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div onClick={onClose} style={modalOverlayStyle}>
      <div onClick={(e) => e.stopPropagation()} style={{ ...modalCardStyle, width: 480 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>
            {isEdit ? "编辑节点" : "新增节点"}
          </div>
          <button onClick={onClose} style={{ all: "unset", cursor: "pointer", color: "var(--ink-3)" }}>
            <I.X size={16} />
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <Lbl>层级</Lbl>
              <select
                style={selectStyle}
                value={level}
                disabled={isEdit}
                onChange={(e) => {
                  setLevel(e.target.value as BusinessMapLevel);
                  setParentId(null);
                  setLinkedHypothesisId(null);
                }}
              >
                {LEVELS.map((lv) => (
                  <option key={lv} value={lv}>{lv}</option>
                ))}
              </select>
            </div>
            <div style={{ flex: 2 }}>
              <Lbl>名称</Lbl>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="节点名称" />
            </div>
          </div>

          {parentLevel && (
            <div>
              <Lbl>父节点（{parentLevel}）</Lbl>
              <select style={selectStyle} value={parentId ?? ""} onChange={(e) => setParentId(e.target.value ? Number(e.target.value) : null)}>
                <option value="">{level === "L2" ? "无（横向支撑域）" : "无"}</option>
                {parentOptions.map((o) => (
                  <option key={o.id} value={o.id}>{o.name}</option>
                ))}
              </select>
            </div>
          )}

          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <Lbl>地图类型</Lbl>
              <select style={selectStyle} value={mapType} onChange={(e) => setMapType(e.target.value as BusinessMapType)}>
                <option value="hypothesis">假设（hypothesis）</option>
                <option value="current">现状（current）</option>
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <Lbl>验证状态</Lbl>
              <select style={selectStyle} value={verificationStatus} onChange={(e) => setVerificationStatus(e.target.value)}>
                {VERIFICATION_STATUSES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>

          {mapType === "current" && (
            <div>
              <Lbl>关联假设节点（可选）</Lbl>
              <select style={selectStyle} value={linkedHypothesisId ?? ""} onChange={(e) => setLinkedHypothesisId(e.target.value ? Number(e.target.value) : null)}>
                <option value="">无</option>
                {hypothesisOptions.map((o) => (
                  <option key={o.id} value={o.id}>{o.name}</option>
                ))}
              </select>
            </div>
          )}

          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <Lbl>置信度</Lbl>
              <select style={selectStyle} value={confidence} onChange={(e) => setConfidence(e.target.value)}>
                <option value="">不标注</option>
                <option value="高">高</option>
                <option value="中">中</option>
                <option value="低">低</option>
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <Lbl>来源类型</Lbl>
              <select style={selectStyle} value={source} onChange={(e) => setSource(e.target.value)}>
                <option value="">不标注</option>
                <option value="搜索采集">搜索采集</option>
                <option value="用户上传">用户上传</option>
                <option value="行业模板">行业模板</option>
                <option value="模型知识">模型知识</option>
              </select>
            </div>
          </div>

          <div>
            <Lbl>高级：payload（JSON，可选，填写则覆盖）</Lbl>
            <TextArea
              rows={3}
              style={{ width: "100%", fontSize: 12, fontFamily: "monospace" }}
              placeholder={isEdit ? "留空则保留原 payload，仅更新上方通用字段" : "留空则仅写入上方通用字段"}
              value={payloadJson}
              onChange={(e) => setPayloadJson(e.target.value)}
            />
          </div>

          {/* 跨项目公开（M5.5.3） */}
          <VisibilityControls
            isPublic={isPublic}
            sharedWith={sharedWith}
            onChange={(v) => {
              setIsPublic(v.is_public);
              setSharedWith(v.shared_with);
            }}
          />
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
          <Btn variant="ghost" onClick={onClose}>取消</Btn>
          <Btn variant="primary" onClick={save} disabled={saving}>{saving ? "保存中…" : "保存"}</Btn>
        </div>
      </div>
    </div>
  );
}

function Lbl({ children }: { children: React.ReactNode }) {
  return <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", marginBottom: 4 }}>{children}</div>;
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
  onEdit,
  onDelete,
  onOpenVisitRecords,
}: {
  node: BusinessMapObject;
  allObjects: BusinessMapObject[];
  onJump: (id: number) => void;
  onEdit: (node: BusinessMapObject) => void;
  onDelete: (node: BusinessMapObject) => void;
  onOpenVisitRecords?: () => void;
}) {
  const p: BusinessMapPayload = node.payload ?? {};
  const color = LEVEL_COLOR[node.level] ?? "var(--ink-3)";
  const linkedHypothesis = node.linked_hypothesis_id
    ? allObjects.find((o) => o.id === node.linked_hypothesis_id)
    : null;

  return (
    <div style={{ fontSize: 13 }}>
      {/* 标题 + 操作 */}
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
        <span style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {node.name}
        </span>
        <button onClick={() => onEdit(node)} title="编辑" style={iconBtnStyle}>
          <I.Edit size={14} />
        </button>
        <button onClick={() => onDelete(node)} title="删除" style={{ ...iconBtnStyle, color: "var(--danger)" }}>
          <I.Trash size={14} />
        </button>
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

      {/* 关联证据（M4.1.10） */}
      <NodeEvidenceSection
        projectId={node.project_id}
        hypothesisId={node.map_type === "current" ? node.linked_hypothesis_id : node.id}
        onOpenVisitRecords={onOpenVisitRecords}
      />
    </div>
  );
}

// ─── 关联证据（M4.1.10：节点详情内证据列表 + 跳转拜访记录） ────

function NodeEvidenceSection({
  projectId,
  hypothesisId,
  onOpenVisitRecords,
}: {
  projectId: number;
  hypothesisId: number | null;
  onOpenVisitRecords?: () => void;
}) {
  const [evidence, setEvidence] = useState<EvidenceSource[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (hypothesisId == null) {
      setEvidence([]);
      return;
    }
    let alive = true;
    setLoading(true);
    api
      .listEvidence(projectId, { related_hypothesis_id: hypothesisId })
      .then((list) => {
        if (alive) setEvidence(list);
      })
      .catch(() => {
        if (alive) setEvidence([]);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [projectId, hypothesisId]);

  return (
    <div style={{ marginTop: 14, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase" }}>
          🔗 关联证据（{evidence.length}）
        </span>
        {onOpenVisitRecords && (
          <button onClick={onOpenVisitRecords} style={linkBtnStyle}>
            查看拜访记录 →
          </button>
        )}
      </div>
      {hypothesisId == null ? (
        <div style={{ fontSize: 11, color: "var(--ink-4)" }}>
          该节点非假设节点且未关联假设，暂无证据联动。
        </div>
      ) : loading ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--ink-3)", fontSize: 11 }}>
          <Spinner size={12} /> 加载证据…
        </div>
      ) : evidence.length === 0 ? (
        <div style={{ fontSize: 11, color: "var(--ink-4)" }}>
          暂无关联证据。在拜访记录中新增证据并关联本假设节点（§7.5 证据验证联动）。
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {evidence.map((ev) => (
            <div key={ev.id} style={{ padding: 10, background: "var(--bg-2)", borderRadius: 8, border: "1px solid var(--line)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, flexWrap: "wrap" }}>
                <Tag tone="neutral">{ev.evidence_type}</Tag>
                <Tag tone={ev.strength === "强" ? "success" : ev.strength === "中" ? "warn" : "neutral"}>
                  强度：{ev.strength}
                </Tag>
                {ev.source_role_name && <span style={{ fontSize: 10, color: "var(--ink-3)" }}>👤 {ev.source_role_name}</span>}
                {ev.review_status !== "reviewed" && (
                  <span style={{ fontSize: 10, color: "var(--warn)" }}>{ev.review_status}</span>
                )}
              </div>
              <div style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.55 }}>{ev.content}</div>
            </div>
          ))}
        </div>
      )}
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
      <div style={{ fontSize: 11, fontWeight: 700, color: "var(--on-accent)", background: "var(--accent)", padding: "6px 10px" }}>
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

// ─── 五维健康视图（M4.1.7：评分表 + 重算 + 手动覆盖） ──────────

function HealthView({
  objects,
  projectId,
  onChanged,
  onJump,
}: {
  objects: BusinessMapObject[];
  projectId: number;
  onChanged: () => void;
  onJump: (node: BusinessMapObject) => void;
}) {
  const toast = useToast();
  const [recomputing, setRecomputing] = useState(false);
  const [editing, setEditing] = useState<BusinessMapObject | null>(null);

  const withHealth = (lv: string) =>
    objects.filter((o) => o.level === lv && o.payload?.fiveDimHealth);

  const l1 = withHealth("L1");
  const l2 = withHealth("L2");
  const l3 = withHealth("L3");
  const empty = l1.length + l2.length + l3.length === 0;

  const recompute = async () => {
    setRecomputing(true);
    try {
      await api.recomputeBusinessMapHealth(projectId);
      toast.showToast("五维健康已按规则重新计算", "success");
      onChanged();
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "重算失败", "error");
    } finally {
      setRecomputing(false);
    }
  };

  return (
    <>
      <Card style={{ flex: 1, padding: 20, overflow: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)" }}>五维健康总览</div>
          <Btn
            size="sm"
            variant="soft"
            icon={<I.Refresh size={13} />}
            onClick={recompute}
            disabled={recomputing}
          >
            {recomputing ? "重算中…" : "重新计算全部"}
          </Btn>
        </div>
        <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 16 }}>
          评分按规则自动计算（M2.1.9）；点击表格行跳转节点详情，「调整」可手动覆盖评分（标记 manual）。
        </div>

        {empty ? (
          <div style={{ padding: 30, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
            <I.Activity size={28} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
            暂无带五维健康的节点。先在对话中生成业务地图（WF07）并采纳，或点「重新计算全部」。
          </div>
        ) : (
          <>
            {l1.length > 0 && <HealthTable title="L1 · 价值链环节" nodes={l1} onJump={onJump} onEdit={setEditing} />}
            {l2.length > 0 && <HealthTable title="L2 · 业务域" nodes={l2} onJump={onJump} onEdit={setEditing} />}
            {l3.length > 0 && <HealthTable title="L3 · 细分场景" nodes={l3} onJump={onJump} onEdit={setEditing} />}
          </>
        )}
      </Card>

      {/* 右：五维解读 */}
      <Card style={{ width: 320, padding: 20, flexShrink: 0, overflow: "auto" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 12 }}>
          📖 五维健康解读
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 12, color: "var(--ink-2)", lineHeight: 1.6 }}>
          {[
            ["L5 数字意识", "战略是否分解到各价值链环节？IT 投资与业务战略是否匹配？", "var(--info)"],
            ["L4 数字神经", "跨环节流程是否顺畅？协同效率如何？变更是否可控？", "var(--accent)"],
            ["L3 数字器官", "核心 IT 系统是否覆盖各环节？系统间是否集成？用户是否愿意用？", "var(--success)"],
            ["L2 数字血液", "跨价值链关键数据是否准确、及时、共享？", "var(--warn)"],
            ["L1 数字骨架", "基础设施是否弹性、经济、可持续？", "var(--danger)"],
          ].map(([title, desc, color]) => (
            <div key={title} style={{ padding: 10, background: "var(--bg-2)", borderRadius: 8, borderLeft: `3px solid ${color}` }}>
              <div style={{ fontWeight: 600, color, marginBottom: 4 }}>{title}</div>
              <div style={{ fontSize: 11 }}>{desc}</div>
            </div>
          ))}
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12, fontSize: 11, color: "var(--ink-3)" }}>
            评分标准：5 分=行业领先 / 3 分=行业平均 / 1 分=严重不足。
          </div>
        </div>
      </Card>

      {editing && (
        <HealthOverrideModal
          node={editing}
          projectId={projectId}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      )}
    </>
  );
}

/** 五维健康评分表（一行一节点，5 维 + 均值） */
function HealthTable({
  title,
  nodes,
  onJump,
  onEdit,
}: {
  title: string;
  nodes: BusinessMapObject[];
  onJump: (node: BusinessMapObject) => void;
  onEdit: (node: BusinessMapObject) => void;
}) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-3)", marginBottom: 8 }}>{title}</div>
      <div style={{ overflow: "auto", border: "1px solid var(--line)", borderRadius: 8 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
          <thead>
            <tr style={{ background: "var(--bg-2)", borderBottom: "2px solid var(--line)" }}>
              <th style={{ padding: "8px 12px", textAlign: "left", fontWeight: 700, color: "var(--ink-3)" }}>节点</th>
              {DIM_ORDER.map((d) => (
                <th key={d.key} style={{ padding: "8px 8px", textAlign: "center", fontWeight: 700, color: "var(--ink-3)" }}>
                  {d.label}
                </th>
              ))}
              <th style={{ padding: "8px 12px", textAlign: "center", fontWeight: 700, color: "var(--ink-3)" }}>均值</th>
              <th style={{ padding: "8px 8px", textAlign: "center", fontWeight: 700, color: "var(--ink-3)" }}></th>
            </tr>
          </thead>
          <tbody>
            {nodes.map((node) => {
              const h = node.payload?.fiveDimHealth!;
              const scores = DIM_ORDER.map((d) => h[d.key]?.score ?? 0);
              const avg = scores.filter((s) => s > 0).length
                ? (scores.reduce((a, b) => a + b, 0) / scores.filter((s) => s > 0).length).toFixed(1)
                : "—";
              return (
                <tr key={node.id} style={{ borderBottom: "1px solid var(--line)" }}>
                  <td
                    style={{ padding: "8px 12px", fontWeight: 500, cursor: "pointer", color: "var(--accent)" }}
                    onClick={() => onJump(node)}
                  >
                    {node.name}
                  </td>
                  {scores.map((s, i) => (
                    <td key={i} style={{ padding: "8px 8px", textAlign: "center" }}>
                      {s > 0 ? <ScoreChip score={s} /> : <span style={{ color: "var(--ink-4)" }}>—</span>}
                    </td>
                  ))}
                  <td style={{ padding: "8px 12px", textAlign: "center", fontWeight: 700 }}>{avg}</td>
                  <td style={{ padding: "8px 8px", textAlign: "center" }}>
                    <button onClick={() => onEdit(node)} style={linkBtnStyle}>调整</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ScoreChip({ score }: { score: number }) {
  return (
    <span
      style={{
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 600,
        background: score <= 2 ? "var(--danger-soft)" : score === 3 ? "var(--warn-soft)" : "var(--success-soft)",
        color: score <= 2 ? "var(--danger)" : score === 3 ? "var(--warn)" : "var(--success)",
      }}
    >
      {score}
    </span>
  );
}

/** 手动覆盖五维健康弹窗 */
function HealthOverrideModal({
  node,
  projectId,
  onClose,
  onSaved,
}: {
  node: BusinessMapObject;
  projectId: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const existing = node.payload?.fiveDimHealth ?? {};
  const [scores, setScores] = useState<Record<string, number>>(() => {
    const init: Record<string, number> = {};
    for (const d of DIM_ORDER) init[d.key] = existing[d.key]?.score ?? 3;
    return init;
  });
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const payload: Record<string, { score: number; desc: string }> = {};
      for (const d of DIM_ORDER) {
        const prev = existing[d.key];
        payload[d.key] = { score: scores[d.key], desc: prev?.desc ?? "" };
      }
      await api.setBusinessMapNodeHealth(projectId, node.id, payload);
      toast.showToast("已手动覆盖五维健康", "success");
      onSaved();
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div onClick={onClose} style={modalOverlayStyle}>
      <div onClick={(e) => e.stopPropagation()} style={modalCardStyle}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>
            手动调整五维健康
            <span style={{ fontSize: 12, color: "var(--ink-3)", fontWeight: 400, marginLeft: 8 }}>{node.name}</span>
          </div>
          <button onClick={onClose} style={{ all: "unset", cursor: "pointer", color: "var(--ink-3)" }}>
            <I.X size={16} />
          </button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {DIM_ORDER.map((d) => (
            <div key={d.key} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: 13, fontWeight: 500, color: "var(--ink-2)", width: 80, flexShrink: 0 }}>{d.label}</span>
              <div style={{ display: "flex", gap: 4 }}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    onClick={() => setScores((p) => ({ ...p, [d.key]: n }))}
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: 6,
                      border: `1px solid ${scores[d.key] === n ? "var(--accent)" : "var(--line)"}`,
                      background: scores[d.key] === n ? "var(--accent)" : "var(--surface)",
                      color: scores[d.key] === n ? "var(--on-accent)" : "var(--ink-2)",
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <span style={{ fontSize: 11, color: "var(--ink-4)" }}>
                {scores[d.key] >= 4 ? "领先" : scores[d.key] === 3 ? "平均" : "不足"}
              </span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
          <Btn variant="ghost" onClick={onClose}>取消</Btn>
          <Btn variant="primary" onClick={save} disabled={saving}>{saving ? "保存中…" : "保存覆盖"}</Btn>
        </div>
      </div>
    </div>
  );
}

const modalOverlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.35)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};
const modalCardStyle: React.CSSProperties = {
  width: 440,
  background: "var(--surface)",
  border: "1px solid var(--line)",
  borderRadius: 12,
  padding: 20,
  boxShadow: "0 8px 32px rgba(0,0,0,0.18)",
};

// ─── 前置分析（M4.1.6：查看 + 编辑） ──────────────────────────

const PREANALYSIS_FIELDS: { key: keyof PreAnalysisInput; label: string; emoji: string; hint: string }[] = [
  { key: "industry_value_chain", label: "行业价值链", emoji: "🏭", hint: "上游→中游→下游，标注客户所在环节" },
  { key: "customer_position", label: "客户行业地位", emoji: "📊", hint: "市场份额/排名/核心竞争力/市场布局" },
  { key: "industry_trends", label: "行业趋势与变化", emoji: "📈", hint: "政策/技术/市场/竞争 PEST 四维度" },
  { key: "strategic_positioning", label: "客户战略定位", emoji: "🎯", hint: "使命/战略重点/数字化态度/近期调整/关键 KPI" },
  { key: "digitalization_drivers", label: "数字化驱动力", emoji: "⚡", hint: "2-3 个关键驱动力，与 L1 五维健康关联" },
];

const EMPTY_FORM: PreAnalysisInput = {
  industry_value_chain: "",
  customer_position: "",
  industry_trends: "",
  strategic_positioning: "",
  digitalization_drivers: "",
};

function PreAnalysisView({ projectId }: { projectId: number }) {
  const toast = useToast();
  const [data, setData] = useState<PreAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<PreAnalysisInput>(EMPTY_FORM);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const pa = await api.getPreAnalysis(projectId);
      setData(pa);
      setForm(pa ? toForm(pa) : EMPTY_FORM);
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "加载前置分析失败", "error");
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const startEdit = () => {
    setForm(data ? toForm(data) : EMPTY_FORM);
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const pa = await api.upsertPreAnalysis(projectId, form);
      setData(pa);
      setForm(toForm(pa));
      setEditing(false);
      toast.showToast("前置分析已保存", "success");
    } catch (e) {
      toast.showToast(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Card style={{ flex: 1, padding: 40, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--ink-3)", fontSize: 13 }}>
          <Spinner size={16} /> 加载前置分析…
        </div>
      </Card>
    );
  }

  return (
    <>
      {/* 左：内容/表单 */}
      <Card style={{ flex: 1, padding: 20, overflow: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)" }}>产业环境与战略定位分析</div>
          {!editing && (
            <Btn size="sm" variant="soft" icon={<I.Edit size={13} />} onClick={startEdit}>
              {data ? "编辑" : "填写"}
            </Btn>
          )}
        </div>

        {!data && !editing ? (
          <div style={{ padding: 30, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
            <I.Search size={28} style={{ color: "var(--ink-4)", marginBottom: 10 }} />
            <div style={{ marginBottom: 12 }}>本项目尚未填写前置分析。</div>
            <Btn size="sm" variant="primary" icon={<I.Plus size={13} />} onClick={startEdit}>
              开始填写
            </Btn>
          </div>
        ) : editing ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {PREANALYSIS_FIELDS.map((f) => (
              <div key={f.key}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)", marginBottom: 4 }}>
                  {f.emoji} {f.label}
                  <span style={{ fontSize: 11, fontWeight: 400, color: "var(--ink-4)", marginLeft: 6 }}>
                    （{f.hint}）
                  </span>
                </div>
                <TextArea
                  rows={3}
                  style={{ width: "100%", fontSize: 13, lineHeight: 1.6 }}
                  placeholder={`请输入${f.label}…`}
                  value={(form[f.key] as string) ?? ""}
                  onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
                />
              </div>
            ))}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
              <Btn variant="ghost" onClick={() => { setEditing(false); setForm(data ? toForm(data) : EMPTY_FORM); }}>
                取消
              </Btn>
              <Btn variant="primary" onClick={save} disabled={saving}>
                {saving ? "保存中…" : "保存"}
              </Btn>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12, fontSize: 13 }}>
            {PREANALYSIS_FIELDS.map((f) => {
              const value = (data as PreAnalysis | null)?.[f.key as keyof PreAnalysis] ?? null;
              return (
                <div key={f.key} style={{ padding: 14, background: "var(--bg-2)", borderRadius: 10, border: "1px solid var(--line)" }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)", marginBottom: 6 }}>
                    {f.emoji} {f.label}
                  </div>
                  <div style={{ color: value ? "var(--ink-2)" : "var(--ink-4)", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
                    {value || "（未填写）"}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* 右：维度说明 */}
      <Card style={{ width: 300, padding: 20, flexShrink: 0, overflow: "auto" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 12 }}>
          📋 分析维度说明
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, fontSize: 12, color: "var(--ink-2)", lineHeight: 1.6 }}>
          <div>
            前置分析回答：<b>为什么客户当前的战略是这样？为什么数字化是它的关键抓手？</b>
          </div>
          <div>五个维度层层递进：行业价值链 → 客户地位 → 行业趋势 → 战略定位 → 数字化驱动力。</div>
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12, color: "var(--ink-3)" }}>
            与 L1 地图的关系：数字化驱动力直接关联 L1 五维健康中的「数字意识」和「数字神经」维度，为后续 L1 价值链健康诊断提供战略上下文。
          </div>
          {data?.updated_at && (
            <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12, fontSize: 11, color: "var(--ink-4)" }}>
              最近更新：{data.updated_at.slice(0, 16).replace("T", " ")}
              {data.created_by_name ? ` · 由 ${data.created_by_name}` : ""}
            </div>
          )}
        </div>
      </Card>
    </>
  );
}

function toForm(pa: PreAnalysis): PreAnalysisInput {
  return {
    industry_value_chain: pa.industry_value_chain ?? "",
    customer_position: pa.customer_position ?? "",
    industry_trends: pa.industry_trends ?? "",
    strategic_positioning: pa.strategic_positioning ?? "",
    digitalization_drivers: pa.digitalization_drivers ?? "",
  };
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

const iconBtnStyle: React.CSSProperties = {
  all: "unset",
  cursor: "pointer",
  color: "var(--ink-3)",
  display: "inline-flex",
  alignItems: "center",
  padding: 4,
  borderRadius: 6,
};
