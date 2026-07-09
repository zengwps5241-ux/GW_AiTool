// 🧪 PROTOTYPE — 拜访记录页面（V2.0 规格 2.5 节）
// 中石油数字化转型项目 模拟拜访记录 + 证据数据
import { useState } from "react";
import { I } from "@/icons";
import { Card } from "@/components/ui";

// ============================================================
// 模拟数据
// ============================================================

type VisitType = "现场访谈" | "电话沟通" | "视频会议" | "邮件往来" | "一句话记录";
type EvidenceType = "客户原话" | "行为观察" | "角色态度信号" | "业务术语";
type EvidenceStrength = "强" | "中" | "弱";

interface EvidenceItem {
  id: string;
  type: EvidenceType;
  strength: EvidenceStrength;
  content: string;
  sourceRole: string;
  relatedHypothesis: string;
  recordedAt: string;
}

interface VisitRecord {
  id: string;
  date: string;
  type: VisitType;
  ourParticipants: string[];
  clientParticipants: string[];
  location: string;
  duration: string;
  summary: string;
  evidenceCount: number;
  verifiedHypotheses: number;
  relatedCards: string[];
  keyTakeaways: string;
  nextSteps: string;
  evidences: EvidenceItem[];
}

const visitRecords: VisitRecord[] = [
  {
    id: "vr-1",
    date: "2026-07-05",
    type: "现场访谈",
    ourParticipants: ["张顾问（项目总监）", "李工（AI架构师）", "小王（咨询顾问）"],
    clientParticipants: ["王国强（信息化部主任）", "李明远（技术负责人）"],
    location: "中国石油大厦 信息化部会议室 1208",
    duration: "2小时15分钟",
    summary: "首次正式方案汇报会。王主任对勘探AI方向给予积极反馈，要求我们两周内提供详细的三期实施规划。李工在技术架构层面提了多个深入问题，主要关注现有系统兼容性和数据安全方案。",
    evidenceCount: 8,
    verifiedHypotheses: 2,
    relatedCards: ["王国强", "李明远"],
    keyTakeaways: "① 勘探AI是最佳切入点，王主任最熟悉此领域；② 数据安全和系统兼容是关键技术门槛；③ 需要'切小切口'——第一期控制在500万以内；④ 两周内提交三期规划+技术白皮书",
    nextSteps: "1. 8月底前完成详细技术白皮书；2. 安排我方架构师与李工团队做深度技术对接；3. 准备勘探AI POC Demo演示环境",
    evidences: [
      { id: "ev-1", type: "客户原话", strength: "强", content: "王主任说：'勘探是我最熟悉的领域，AI能不能帮我们把探井成功率从62%提到70%？如果能，这个项目我全力支持。'", sourceRole: "王国强", relatedHypothesis: "勘探与评估(L1)", recordedAt: "2026-07-05 14:20" },
      { id: "ev-2", type: "客户原话", strength: "强", content: "王主任补充：'集团现在有明确要求，数字化转型要'可衡量、可考核'，你们的设计要把这个体现进去。'", sourceRole: "王国强", relatedHypothesis: "数据与AI平台域(L2)", recordedAt: "2026-07-05 14:25" },
      { id: "ev-3", type: "行为观察", strength: "中", content: "讨论到具体技术方案时，李工拿出自己的笔记本，上面提前列了7个问题，逐一询问。准备充分，技术功底扎实。", sourceRole: "李明远", relatedHypothesis: "数据与AI平台域(L2)", recordedAt: "2026-07-05 14:45" },
      { id: "ev-4", type: "角色态度信号", strength: "强", content: "王主任在会议结束时主动提出：'我安排李明远下周跟你们做技术对接，你们好好交流一下。'——这是推动项目落地的强烈信号", sourceRole: "王国强", relatedHypothesis: "勘探与评估(L1)", recordedAt: "2026-07-05 15:50" },
      { id: "ev-5", type: "客户原话", strength: "中", content: "李工提问：'你们的架构跟我们的SAP系统怎么对接？我们刚花了3年做完ERP升级，不能推倒重来。'", sourceRole: "李明远", relatedHypothesis: "智能炼化域(L2)", recordedAt: "2026-07-05 14:50" },
      { id: "ev-6", type: "业务术语", strength: "弱", content: "客户反复提及'数据湖'、'API网关'、'微服务'等术语，表明技术认知水平较高，方案中可以适当使用技术语言", sourceRole: "王国强/李明远", relatedHypothesis: "数据与AI平台域(L2)", recordedAt: "2026-07-05 全程" },
      { id: "ev-7", type: "客户原话", strength: "强", content: "王主任提到预算问题时低声说：'集团审批流程比较长，你们如果分三期报，第一期走科技专项通道，我可以帮你们推动。'——暗示可分阶段规避大额审批", sourceRole: "王国强", relatedHypothesis: "N/A", recordedAt: "2026-07-05 15:30" },
      { id: "ev-8", type: "行为观察", strength: "中", content: "汇报过程中，王主任多次点头并在自己的笔记本上做记录，特别是在我们展示XX油田的实际案例效果时", sourceRole: "王国强", relatedHypothesis: "勘探与评估(L1)", recordedAt: "2026-07-05 全程" },
    ],
  },
  {
    id: "vr-2",
    date: "2026-07-01",
    type: "现场访谈",
    ourParticipants: ["张顾问（项目总监）", "小王（咨询顾问）"],
    clientParticipants: ["陈晓燕（勘探事业部副经理）", "刘明（地质师）"],
    location: "勘探开发研究院 302会议室",
    duration: "1小时30分钟",
    summary: "Demo演示+业务调研。向勘探一线用户展示AI辅助井位评价原型，收到积极但务实的反馈。陈晓燕提供了真实的手工评价模板，要求我们用实际油田数据再跑一次。",
    evidenceCount: 6,
    verifiedHypotheses: 1,
    relatedCards: ["陈晓燕"],
    keyTakeaways: "① 一线用户对AI的核心诉求是'好用，不增加工作量'；② 陈晓燕是潜在的用户侧Champion；③ 获得真实业务模板，可用作产品设计的参考",
    nextSteps: "1. 基于陈晓燕提供的模板，开发AI辅助评价原型；2. 用更多真实井位数据验证模型效果",
    evidences: [
      { id: "ev-9", type: "客户原话", strength: "强", content: "陈晓燕说：'我不是不相信AI，我是被之前几个数字化项目搞怕了——花了几百万开发，最后没人用。你们这个要真的能帮我们干活才行。'", sourceRole: "陈晓燕", relatedHypothesis: "勘探与评估(L1)", recordedAt: "2026-07-01 10:15" },
      { id: "ev-10", type: "行为观察", strength: "强", content: "Demo演示后，陈晓燕主动拿出他们目前手工做井位评价的Excel模板，详细解释了每个字段的业务含义。这是极大的信任信号。", sourceRole: "陈晓燕", relatedHypothesis: "探井井位智能优选(L3)", recordedAt: "2026-07-01 10:45" },
      { id: "ev-11", type: "客户原话", strength: "中", content: "地质师刘明指出：'我们这块构造比较复杂，你拿公开数据集训练出来的模型不一定适用。最好用我们自己的数据fine-tune一下。'", sourceRole: "刘明", relatedHypothesis: "地质研究域(L2)", recordedAt: "2026-07-01 11:00" },
      { id: "ev-12", type: "角色态度信号", strength: "中", content: "陈晓燕会后主动加微信，发了他们目前使用的井位评价模板和工作流程图。从'反对'到'中立'的态度转变确有发生。", sourceRole: "陈晓燕", relatedHypothesis: "勘探与评估(L1)", recordedAt: "2026-07-01 11:30" },
      { id: "ev-13", type: "客户原话", strength: "中", content: "陈晓燕评价：'你们这个Demo用我们的数据跑出来结果还算合理，给我看看更多井位的效果。如果是准的，我可以帮你们跟领导说。'", sourceRole: "陈晓燕", relatedHypothesis: "探井井位智能优选(L3)", recordedAt: "2026-07-01 11:10" },
      { id: "ev-14", type: "业务术语", strength: "弱", content: "客户频繁使用'圈闭'、'烃源岩'、'储层物性'、'AVO属性'等石油地质专业术语，要求团队加强行业知识储备", sourceRole: "陈晓燕/刘明", relatedHypothesis: "地质研究域(L2)", recordedAt: "2026-07-01 全程" },
    ],
  },
  {
    id: "vr-3",
    date: "2026-07-02",
    type: "视频会议",
    ourParticipants: ["张顾问（项目总监）", "赵经理（商务负责人）"],
    clientParticipants: ["赵建国（财务部副总经理）"],
    location: "线上（腾讯会议）",
    duration: "45分钟",
    summary: "项目立项预算沟通会。赵总对项目总投入和ROI测算提出了尖锐质疑，是目前最直接的反对声音。需要准备更完整的财务测算模型。",
    evidenceCount: 4,
    verifiedHypotheses: 0,
    relatedCards: ["赵建国"],
    keyTakeaways: "① 赵总是当前项目推进的最大阻力点；② 核心诉求不是反对AI，而是担心预算失控和ROI无法量化；③ 需要提供同行业AI项目的ROI案例",
    nextSteps: "1. 准备详细的财务测算模型；2. 收集3-5个能源行业AI项目的实际ROI数据；3. 提出'分期支付+里程碑验收'的付款方案",
    evidences: [
      { id: "ev-15", type: "客户原话", strength: "强", content: "赵总原话：'2000多万投AI？你们给我算算几年回本？现在集团对IT投资回报要求很严，说不清楚这个，立项会我都不能签字。'", sourceRole: "赵建国", relatedHypothesis: "N/A", recordedAt: "2026-07-02 15:10" },
      { id: "ev-16", type: "角色态度信号", strength: "强", content: "赵总全程面色严肃，只在追问ROI和预算细节时主动发言。会议结束时说'你们再好好算算'，态度偏冷但并未完全关闭沟通通道。", sourceRole: "赵建国", relatedHypothesis: "N/A", recordedAt: "2026-07-02 全程" },
      { id: "ev-17", type: "客户原话", strength: "中", content: "赵总质疑：'AI项目没有行业定价标准，你们报价2000万的依据是什么？硬件成本、人力成本、license成本各占多少？'", sourceRole: "赵建国", relatedHypothesis: "N/A", recordedAt: "2026-07-02 15:25" },
      { id: "ev-18", type: "行为观察", strength: "中", content: "赵总在会议结束前独自留下2分钟，私下跟张顾问说：'我不是针对你们，是集团最近对IT预算确实卡得很紧，你们把ROI算扎实，我可以帮忙推动。'——有转机空间", sourceRole: "赵建国", relatedHypothesis: "N/A", recordedAt: "2026-07-02 15:45" },
    ],
  },
  {
    id: "vr-4",
    date: "2026-06-20",
    type: "现场访谈",
    ourParticipants: ["张顾问（项目总监）", "李工（AI架构师）", "小王（咨询顾问）"],
    clientParticipants: ["张明辉（科技部主任）", "王国强（信息化部主任）", "李明远（技术负责人）"],
    location: "中国石油大厦 科技部会议室 1502",
    duration: "2小时",
    summary: "技术交流会。重点展示AI平台的架构设计、安全方案和成功案例。张明辉主任对国际对标案例兴趣浓厚，建议将项目定位与集团'十四五科技规划'对齐。",
    evidenceCount: 7,
    verifiedHypotheses: 1,
    relatedCards: ["王国强", "张明辉", "李明远"],
    keyTakeaways: "① 张主任是重要的内部推手，可帮助项目获取科技专项支持；② 方案需与集团科技规划对齐，体现前瞻性；③ 李工态度从'反对'转变为'中立'",
    nextSteps: "1. 在方案中加入国际对标案例；2. 研究集团'十四五科技规划'，确保项目定位一致；3. 继续跟进李工的技术疑问",
    evidences: [
      { id: "ev-19", type: "客户原话", strength: "强", content: "张主任说：'我们集团的十四五科技规划里明确写了智能化勘探开发方向，你们这个项目如果能纳入科技专项，资金渠道会顺畅很多。'", sourceRole: "张明辉", relatedHypothesis: "勘探与评估(L1)", recordedAt: "2026-06-20 10:30" },
      { id: "ev-20", type: "行为观察", strength: "中", content: "张主任在会议后私下给我们发了3份国际石油公司AI应用的研究报告（Shell、BP、Saudi Aramco），说'你们参考一下国际做法'", sourceRole: "张明辉", relatedHypothesis: "N/A", recordedAt: "2026-06-20 会后" },
      { id: "ev-21", type: "角色态度信号", strength: "强", content: "李工在会后表示：'你们的架构设计确实考虑得比较周全'——这是态度转变的关键信号，之前他一直是最强的技术质疑者", sourceRole: "李明远", relatedHypothesis: "数据与AI平台域(L2)", recordedAt: "2026-06-20 11:45" },
      { id: "ev-22", type: "客户原话", strength: "中", content: "王国强补充：'老张说得对，你们研究一下集团的科技规划文件，把项目包装成'智能化勘探开发示范工程'，这样从上往下推比从下往上推快。'", sourceRole: "王国强", relatedHypothesis: "N/A", recordedAt: "2026-06-20 10:45" },
    ],
  },
  {
    id: "vr-5",
    date: "2026-05-15",
    type: "电话沟通",
    ourParticipants: ["张顾问（项目总监）"],
    clientParticipants: ["王国强（信息化部主任）"],
    location: "电话",
    duration: "30分钟",
    summary: "初次接触。通过行业关系获得王主任手机号码，进行了一次简短但高质量的电话沟通。王主任对AI在勘探领域的应用有初步兴趣，同意安排见面。",
    evidenceCount: 2,
    verifiedHypotheses: 0,
    relatedCards: ["王国强"],
    keyTakeaways: "① 王主任是技术型管理者，初次沟通需要体现专业度；② 对勘探领域AI应用有明确兴趣；③ 要求'先看案例再谈合作'",
    nextSteps: "1. 准备勘探AI案例集和Demo演示；2. 安排正式拜访",
    evidences: [
      { id: "ev-23", type: "客户原话", strength: "中", content: "王主任：'AI我们确实在看，但市场上做这块的太多了，你们有什么差异化？有没有实际的油田案例？'", sourceRole: "王国强", relatedHypothesis: "N/A", recordedAt: "2026-05-15 14:15" },
    ],
  },
];

// ============================================================
// 组件
// ============================================================

const MOCK_PROJECTS = [
  { id: "1", name: "中石油 / 数字化转型项目" },
  { id: "2", name: "中信科 / 信创迁移项目" },
];

const visitTypeColor = (t: VisitType) => {
  if (t === "现场访谈") return "var(--accent)";
  if (t === "电话沟通") return "var(--info)";
  if (t === "视频会议") return "var(--success)";
  if (t === "邮件往来") return "var(--ink-3)";
  return "var(--warn)";
};

const strengthColor = (s: EvidenceStrength) => s === "强" ? "var(--success)" : s === "中" ? "var(--warn)" : "var(--ink-3)";

const evidenceTypeLabel: Record<EvidenceType, string> = {
  "客户原话": "💬 客户原话",
  "行为观察": "👁️ 行为观察",
  "角色态度信号": "🎯 态度信号",
  "业务术语": "📖 业务术语",
};

export default function VisitRecordsPage() {
  const [selectedProject, setSelectedProject] = useState(MOCK_PROJECTS[0].id);
  const [filterType, setFilterType] = useState("全部");
  const [filterStrength, setFilterStrength] = useState("全部");
  const [filterRole, setFilterRole] = useState("全部");
  const [expandedVisit, setExpandedVisit] = useState<string | null>("vr-1");

  // 计算总证据数
  const totalEvidences = visitRecords.reduce((sum, v) => sum + v.evidences.length, 0);
  const allRoles = [...new Set(visitRecords.flatMap(v => v.relatedCards))];

  // 过滤证据
  const filteredEvidences = visitRecords.flatMap(v =>
    v.evidences
      .filter(e => filterType === "全部" || e.type === filterType)
      .filter(e => filterStrength === "全部" || e.strength === filterStrength)
      .filter(e => filterRole === "全部" || e.sourceRole.includes(filterRole))
      .map(e => ({ ...e, visitDate: v.date, visitId: v.id }))
  );

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* 顶部栏 */}
      <div style={{
        padding: "12px 20px", borderBottom: "1px solid var(--line)",
        background: "var(--bg)", display: "flex", alignItems: "center", gap: 16, flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <I.Briefcase size={16} style={{ color: "var(--ink-3)" }} />
          <select value={selectedProject} onChange={(e) => setSelectedProject(e.target.value)}
            style={{
              fontFamily: "inherit", fontSize: 14, fontWeight: 500, color: "var(--ink)",
              background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8,
              padding: "6px 12px", cursor: "pointer",
            }}>
            {MOCK_PROJECTS.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>拜访次数: <b style={{ color: "var(--ink)" }}>{visitRecords.length}</b></span>
        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>涉及角色: <b style={{ color: "var(--ink)" }}>{allRoles.length}</b></span>
        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>总证据: <b style={{ color: "var(--ink)" }}>{totalEvidences}</b></span>
        <span style={{ fontSize: 12, color: "var(--success)" }}>
          已验证假设: <b>{visitRecords.reduce((sum, v) => sum + v.verifiedHypotheses, 0)}</b>
        </span>
      </div>

      {/* 主内容 */}
      <div style={{ flex: 1, overflow: "auto", padding: 20, display: "flex", gap: 20 }}>
        {/* 左侧：拜访记录时间线 */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 12 }}>
          {visitRecords.map(v => (
            <Card key={v.id} style={{ padding: 0, overflow: "hidden" }}>
              {/* 拜访卡片头部 */}
              <div
                onClick={() => setExpandedVisit(expandedVisit === v.id ? null : v.id)}
                style={{
                  padding: "16px 20px", cursor: "pointer", display: "flex", alignItems: "center", gap: 14,
                  transition: "background 120ms",
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-2)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
              >
                {/* 日期 */}
                <div style={{ textAlign: "center", flexShrink: 0, width: 56 }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "var(--ink)", lineHeight: 1 }}>{v.date.slice(8)}</div>
                  <div style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 2 }}>{v.date.slice(5, 7)}月</div>
                </div>
                {/* 类型标签 */}
                <span style={{
                  padding: "3px 10px", borderRadius: 999, fontSize: 11, fontWeight: 600,
                  background: visitTypeColor(v.type) + "20", color: visitTypeColor(v.type),
                  flexShrink: 0,
                }}>{v.type}</span>
                {/* 摘要 */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v.summary.slice(0, 50)}...</div>
                  <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>
                    {v.clientParticipants.join("、")} · {v.duration}
                  </div>
                </div>
                {/* 统计 */}
                <div style={{ display: "flex", gap: 16, fontSize: 11, color: "var(--ink-3)", flexShrink: 0 }}>
                  <span title="证据数">📎 {v.evidenceCount}</span>
                  <span title="已验证假设">✅ {v.verifiedHypotheses}</span>
                </div>
                <I.ChevronDown size={14} style={{
                  color: "var(--ink-4)", flexShrink: 0,
                  transform: expandedVisit === v.id ? "rotate(180deg)" : "none",
                  transition: "transform 200ms",
                }} />
              </div>

              {/* 展开详情 */}
              {expandedVisit === v.id && (
                <div style={{ borderTop: "1px solid var(--line)", padding: "16px 20px", background: "var(--bg)" }}>
                  {/* 基本信息 */}
                  <div style={{ display: "flex", gap: 20, marginBottom: 16, fontSize: 12, flexWrap: "wrap" }}>
                    <div><span style={{ color: "var(--ink-3)" }}>我方参与：</span><span style={{ fontWeight: 500 }}>{v.ourParticipants.join("、")}</span></div>
                    <div><span style={{ color: "var(--ink-3)" }}>客户参与：</span><span style={{ fontWeight: 500 }}>{v.clientParticipants.join("、")}</span></div>
                    <div><span style={{ color: "var(--ink-3)" }}>地点：</span>{v.location}</div>
                    <div><span style={{ color: "var(--ink-3)" }}>时长：</span>{v.duration}</div>
                  </div>

                  {/* Key Takeaways */}
                  <div style={{
                    padding: "12px 14px", background: "var(--accent-soft)", borderRadius: 8,
                    marginBottom: 14, fontSize: 12, lineHeight: 1.6,
                  }}>
                    <div style={{ fontWeight: 700, color: "var(--accent)", marginBottom: 6 }}>💡 关键洞察</div>
                    {v.keyTakeaways}
                  </div>

                  {/* Next Steps */}
                  <div style={{
                    padding: "12px 14px", background: "var(--info-soft)", borderRadius: 8,
                    marginBottom: 16, fontSize: 12, lineHeight: 1.6,
                  }}>
                    <div style={{ fontWeight: 700, color: "var(--info)", marginBottom: 6 }}>📋 下一步行动</div>
                    {v.nextSteps}
                  </div>

                  {/* 证据列表 */}
                  <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 10 }}>
                      证据清单 ({v.evidences.length}条)
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {v.evidences.map(e => (
                        <div key={e.id} style={{
                          display: "flex", gap: 10, padding: "10px 12px",
                          background: "var(--surface)", borderRadius: 8, border: "1px solid var(--line)",
                          fontSize: 12,
                        }}>
                          <div style={{
                            width: 6, height: 6, borderRadius: 999, background: strengthColor(e.strength),
                            flexShrink: 0, marginTop: 5,
                          }} />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ lineHeight: 1.6, color: "var(--ink-2)", marginBottom: 6 }}>{e.content}</div>
                            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                              <span style={{ padding: "1px 6px", borderRadius: 4, fontSize: 10, background: "var(--bg-3)", color: "var(--ink-3)" }}>
                                {evidenceTypeLabel[e.type]}
                              </span>
                              <span style={{
                                padding: "1px 6px", borderRadius: 4, fontSize: 10,
                                background: strengthColor(e.strength) + "18", color: strengthColor(e.strength), fontWeight: 500,
                              }}>
                                {e.strength}证据
                              </span>
                              <span style={{ padding: "1px 6px", borderRadius: 4, fontSize: 10, background: "var(--info-soft)", color: "var(--info)" }}>
                                {e.sourceRole}
                              </span>
                              {e.relatedHypothesis !== "N/A" && (
                                <span style={{ padding: "1px 6px", borderRadius: 4, fontSize: 10, background: "var(--accent-soft)", color: "var(--accent)", fontWeight: 500 }}>
                                  🔗 {e.relatedHypothesis}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>

        {/* 右侧证据筛选面板 */}
        <Card style={{ width: 320, padding: 20, flexShrink: 0, alignSelf: "flex-start", position: "sticky", top: 0 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 16 }}>
            证据筛选
          </div>

          {/* 类型筛选 */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 500, color: "var(--ink-3)", marginBottom: 5 }}>证据类型</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {["全部", "客户原话", "行为观察", "角色态度信号", "业务术语"].map(t => (
                <button key={t} onClick={() => setFilterType(t)}
                  style={{
                    padding: "3px 10px", borderRadius: 999, fontSize: 11, fontWeight: 500,
                    border: filterType === t ? "1px solid var(--accent)" : "1px solid var(--line)",
                    background: filterType === t ? "var(--accent-soft)" : "transparent",
                    color: filterType === t ? "var(--accent)" : "var(--ink-2)",
                    cursor: "pointer", fontFamily: "inherit", transition: "all 120ms",
                  }}>
                  {t === "全部" ? "全部" : evidenceTypeLabel[t as EvidenceType]}
                </button>
              ))}
            </div>
          </div>

          {/* 强度筛选 */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 500, color: "var(--ink-3)", marginBottom: 5 }}>证据强度</div>
            <div style={{ display: "flex", gap: 6 }}>
              {["全部", "强", "中", "弱"].map(s => (
                <button key={s} onClick={() => setFilterStrength(s)}
                  style={{
                    padding: "4px 14px", borderRadius: 6, fontSize: 12, fontWeight: 500,
                    border: filterStrength === s ? "1px solid var(--accent)" : "1px solid var(--line)",
                    background: filterStrength === s ? "var(--accent-soft)" : "transparent",
                    color: filterStrength === s ? "var(--accent)" : s === "强" ? "var(--success)" : s === "中" ? "var(--warn)" : "var(--ink-2)",
                    cursor: "pointer", fontFamily: "inherit", transition: "all 120ms",
                  }}>
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* 角色筛选 */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 500, color: "var(--ink-3)", marginBottom: 5 }}>关联角色</div>
            <select value={filterRole} onChange={(e) => setFilterRole(e.target.value)}
              style={{
                width: "100%", fontFamily: "inherit", fontSize: 12, background: "var(--surface)",
                border: "1px solid var(--line)", borderRadius: 6, padding: "6px 10px", color: "var(--ink)",
              }}>
              <option value="全部">全部角色</option>
              {allRoles.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>

          {/* 筛选结果 */}
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-2)", marginBottom: 10 }}>
              筛选结果 ({filteredEvidences.length}条)
            </div>
            {filteredEvidences.length === 0 ? (
              <div style={{ fontSize: 12, color: "var(--ink-3)", textAlign: "center", padding: 20 }}>无匹配证据</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 400, overflow: "auto" }}>
                {filteredEvidences.map((e, i) => (
                  <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid var(--line)", fontSize: 11 }}>
                    <div style={{ display: "flex", gap: 4, marginBottom: 4, flexWrap: "wrap" }}>
                      <span style={{ padding: "0 5px", borderRadius: 3, background: "var(--bg-3)", fontSize: 9, color: "var(--ink-3)" }}>
                        {e.visitDate}
                      </span>
                      <span style={{ padding: "0 5px", borderRadius: 3, background: "var(--info-soft)", fontSize: 9, color: "var(--info)" }}>
                        {e.sourceRole}
                      </span>
                      <span style={{
                        padding: "0 5px", borderRadius: 3,
                        background: strengthColor(e.strength as EvidenceStrength) + "18",
                        color: strengthColor(e.strength as EvidenceStrength), fontSize: 9, fontWeight: 500,
                      }}>
                        {e.strength}
                      </span>
                    </div>
                    <div style={{ lineHeight: 1.5, color: "var(--ink-2)" }}>{e.content.slice(0, 80)}{e.content.length > 80 ? "..." : ""}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 统计摘要 */}
          <div style={{ marginTop: 16, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 8 }}>证据统计</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11 }}>
              {(["强", "中", "弱"] as EvidenceStrength[]).map(s => {
                const count = visitRecords.flatMap(v => v.evidences).filter(e => e.strength === s).length;
                return (
                  <div key={s} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ width: 6, height: 6, borderRadius: 999, background: strengthColor(s) }} />
                      <span style={{ color: "var(--ink-2)" }}>{s}证据</span>
                    </div>
                    <b>{count}</b>
                    <div style={{ width: 60, height: 4, background: "var(--bg-3)", borderRadius: 2, overflow: "hidden" }}>
                      <div style={{
                        width: `${(count / totalEvidences) * 100}%`, height: "100%",
                        background: strengthColor(s), borderRadius: 2, transition: "width 300ms",
                      }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
