// 🧪 PROTOTYPE — 营销地图页面（V2.0 规格 2.4 节）
// 中石油数字化转型项目 模拟角色卡数据
// 已补全全部字段：竞品历史、KPI分离、隐性诉求、竞品态度、综合评分、置信度、角色识别知识库等
import { useState, useMemo } from "react";
import { I } from "@/icons";
import { Card, Tag } from "@/components/ui";

// ============================================================
// 类型定义（对齐营销地图设计文档 V2.0 全部字段）
// ============================================================

type RoleType = "economic_decision_maker" | "technical_evaluator" | "user" | "coach_supporter" | "procurement_finance";
type StanceLevel = "支持" | "中立" | "反对" | "观望";
type GradeLevel = "Champion" | "倾向我方" | "中立" | "反对";

interface StakeholderCard {
  id: string;
  name: string;
  position: string;
  department: string;
  reportsTo: string;
  contactInfo?: string;            // 联系方式（新增）
  roleType: RoleType;
  decisionPower: "最终决策" | "技术把关" | "推荐建议" | "影响者" | "信息提供";

  // 客观信息
  background: {
    education: string;
    previousCompanies: string;
    personality: string;
    communicationPreference: string;
    relationships: string;
  };

  // 主观信息
  subjective: {
    stance: StanceLevel;
    explicitKPI: string;           // 显性KPI — 从 interests 中分离（新增）
    personalMotivation: string;    // 隐性个人诉求 — 从 interests 中分离（新增）
    attitudeToUs: string;          // 对我方方案的态度
    attitudeToCompetitor: string;  // 对竞品的态度（新增）
    engagement: number;            // 参与度 0-10
    influence: number;             // 影响力 0-10
    support: number;               // 支持度 0-10
    compositeScore: number;        // 综合评分 = 参与度×0.3 + 影响力×0.4 + 支持度×0.3（新增）
    gradeLevel: GradeLevel;        // 评分等级（新增）
    confidence: "高" | "中" | "低"; // 置信度（新增）
    coreConcerns: string;
    leverage: string;
  };

  // 历史合作
  historyWithUs: string;           // 与我方交集
  historyWithCompetitor: string;   // 与竞品交集（新增）

  // 行为分析
  behaviors: { observation: string; interpretation: string; suggestedAction: string }[];

  // 态度变化
  stanceLog: { date: string; from: StanceLevel; to: StanceLevel; reason: string }[];
}

interface TalkScript {
  id: string;
  stakeholderCardId: string;
  roleType: RoleType;
  scenario: string;
  content: string;
}

/** 知识库：角色识别特征 */
interface RoleRecognition {
  roleType: RoleType;
  bodyLanguage: string;
  speechPattern: string;
  typicalResponse: string;
  identificationSignal: string;
}

/** 知识库：行为分析速查 */
interface BehaviorQuickRef {
  observation: string;
  interpretation: string;
  suggestedAction: string;
}

// ============================================================
// 模拟数据
// ============================================================

const MOCK_PROJECTS = [
  { id: "1", name: "中石油 / 数字化转型项目" },
  { id: "2", name: "中信科 / 信创迁移项目" },
];

/** 计算综合评分和等级 */
function calcGrade(engagement: number, influence: number, support: number): { compositeScore: number; gradeLevel: GradeLevel } {
  const raw = engagement * 0.3 + influence * 0.4 + support * 0.3;
  const compositeScore = Math.round(raw);
  let gradeLevel: GradeLevel;
  if (compositeScore >= 8) gradeLevel = "Champion";
  else if (compositeScore >= 5) gradeLevel = "倾向我方";
  else if (compositeScore >= 3) gradeLevel = "中立";
  else gradeLevel = "反对";
  return { compositeScore, gradeLevel };
}

const wgq = calcGrade(9, 9, 8);
const lmy = calcGrade(8, 6, 4);
const zjg = calcGrade(4, 7, 2);
const zmh = calcGrade(6, 8, 7);
const cxy = calcGrade(5, 5, 5);

const stakeholderCards: StakeholderCard[] = [
  {
    id: "sc-1", name: "王国强", position: "信息化部主任", department: "信息化部",
    reportsTo: "集团副总裁", contactInfo: "wangguoqiang@cnpc.com.cn / 010-XXXX-XXXX",
    roleType: "economic_decision_maker", decisionPower: "最终决策",
    background: {
      education: "清华大学计算机科学博士，MIT Sloan访问学者",
      previousCompanies: "中石油工作22年，历任勘探开发研究院计算所所长、集团科技部副主任",
      personality: "技术出身的管理者，理性务实，注重数据论证。对新技术的态度是'先小规模验证再推广'",
      communicationPreference: "偏好结构化汇报（PPT+数据报告），不喜欢冗长口头汇报。邮件回复及时，但要求简洁明确",
      relationships: "与集团科技部张主任关系密切，曾共事10年；在信息化部内部威望高，下属普遍尊重其专业判断",
    },
    subjective: {
      stance: "支持",
      explicitKPI: "集团信息化考核达标；年度数字化项目预算执行率≥95%",
      personalMotivation: "希望通过AI中台统一管理集团分散的数字化项目，树立行业数字化转型标杆，为晋升集团CIO积累政绩",
      attitudeToUs: "主动推动项目立项，已经在部门内部组织了3次AI技术研讨会。对供应商选择标准明确：技术领先性>行业经验>价格",
      attitudeToCompetitor: "认为华为云方案偏标准化产品、不够贴合油气业务场景；认为阿里云数据能力强但行业理解深度不足",
      engagement: 9, influence: 9, support: 8,
      compositeScore: wgq.compositeScore, gradeLevel: wgq.gradeLevel, confidence: "高",
      coreConcerns: "① 数据安全合规（国企敏感数据不能上公有云）；② AI项目ROI难以量化，担心'大投入小产出'；③ 现有IT团队AI能力不足，过度依赖外部供应商",
      leverage: "① 引用'国资委87号文'关于央企数字化转型的要求施压；② 联合科技部张主任形成技术+行政双线推动；③ 从勘探领域（他最熟悉）先做POC，用效果说话",
    },
    historyWithUs: "已合作2个月，建立良好信任关系。2026-05首次拜访，6月做技术交流会，7月初提交初步方案。",
    historyWithCompetitor: "华为云在2025年做过AI中台交流，但未进入正式采购流程；阿里云目前在为其提供数据湖底层基础设施服务",
    behaviors: [
      { observation: "首次拜访时，他提前准备了3页问题清单，全部涉及技术架构细节", interpretation: "深度技术背景+对项目高度重视，需要我们用同等专业度回应", suggestedAction: "下次拜访前准备详细技术白皮书，安排我方架构师参与交流" },
      { observation: "会议结束时主动提出安排IT团队下周与我们做技术对接", interpretation: "认可我们的专业能力，正在推动项目加速落地", suggestedAction: "及时跟进技术对接会议，提供Demo演示环境" },
      { observation: "在讨论预算时多次提到'集团审批流程长'，建议分阶段立项", interpretation: "正在帮我们找最可行的推动路径，暗示需要'切小切口'", suggestedAction: "调整方案为三期规划，第一期聚焦勘探AI，预算控制在500万以内" },
    ],
    stanceLog: [
      { date: "2026-05-15", from: "观望", to: "中立", reason: "首次拜访后认可团队专业度，但需要更多证据" },
      { date: "2026-06-20", from: "中立", to: "支持", reason: "看了勘探AI Demo后转变态度，认为'技术路线可行'" },
    ],
  },
  {
    id: "sc-2", name: "李明远", position: "高级工程师 / 技术负责人", department: "信息化部",
    reportsTo: "王国强", contactInfo: "limingyuan@cnpc.com.cn",
    roleType: "technical_evaluator", decisionPower: "技术把关",
    background: {
      education: "中国石油大学计算机硕士",
      previousCompanies: "中石油工作15年，一直做信息化建设，主导过ERP升级、数据中心迁移",
      personality: "谨慎保守，细节控。对技术方案要求'刨根问底'，最反感'画饼'式PPT",
      communicationPreference: "喜欢技术白皮书和架构图，最好有Demo。接受微信随时沟通技术问题",
      relationships: "在信息化部有3名嫡系工程师团队；与华为云、阿里云的技术团队有长期联系",
    },
    subjective: {
      stance: "中立",
      explicitKPI: "系统可用性≥99.9%；新系统与现有IT架构兼容率100%；技术方案评审一次通过率≥90%",
      personalMotivation: "希望引入的新系统技术架构先进但不过于激进，不影响现有系统稳定性，不增加运维团队负担；个人期望在信创替代项目中展现技术把控能力",
      attitudeToUs: "对AI持谨慎态度，认为'AI是锦上添花，先解决数据治理问题'。多次质疑AI模型的准确率和可解释性，但认可我方架构能力",
      attitudeToCompetitor: "与华为云技术团队关系好，认可其基础设施能力；认为阿里云方案'太互联网化'不适合国企场景",
      engagement: 8, influence: 6, support: 4,
      compositeScore: lmy.compositeScore, gradeLevel: lmy.gradeLevel, confidence: "中",
      coreConcerns: "① 担心新系统与现有SAP、OA系统集成困难；② AI模型'黑盒'，出了问题无法排查；③ 团队技能跟不上，运维成问题",
      leverage: "① 提供详细的技术对接方案和API文档，证明兼容性；② 安排POC环境中让他团队亲自测试；③ 引入可解释AI(XAI)模块",
    },
    historyWithUs: "只见过2次，还在建立信任阶段。需要更多技术层面的深入交流。",
    historyWithCompetitor: "与华为云有长期技术合作关系，华为云目前为其提供部分IaaS/PaaS服务；2024年参与过华为云的AI平台技术评测",
    behaviors: [
      { observation: "技术交流会上连续追问了7个架构细节问题，包括数据流、容灾方案、并发处理", interpretation: "技术功底扎实，是真想评估方案可行性，不是故意刁难", suggestedAction: "下次带架构师做深度技术交流，准备完整的架构设计文档" },
      { observation: "私下微信询问'你们的方案和华为云的方案有什么区别'", interpretation: "正在做供应商对比，对我们有兴趣但还没下决心", suggestedAction: "准备竞品对比分析材料，客观列出差异化优势" },
    ],
    stanceLog: [
      { date: "2026-06-20", from: "反对", to: "中立", reason: "技术交流后认可架构能力，但仍保留对AI模型可靠性的质疑" },
    ],
  },
  {
    id: "sc-3", name: "赵建国", position: "财务部副总经理", department: "财务部",
    reportsTo: "集团总会计师", contactInfo: "zhaojianguo@cnpc.com.cn",
    roleType: "procurement_finance", decisionPower: "推荐建议",
    background: {
      education: "中央财经大学会计学本科，北大EMBA",
      previousCompanies: "中石油工作20年，长期在财务线",
      personality: "典型的财务思维——务实、抠细节、重视ROI和风险防控。任何提案第一反应是'花多少钱、什么时候回本'",
      communicationPreference: "简洁的财务测算表+风险分析报告。会议上话少但关键问题一针见血",
      relationships: "与集团采购中心有紧密协作；与王主任（信息化部）在工作上有过多次合作",
    },
    subjective: {
      stance: "反对",
      explicitKPI: "年度IT采购预算偏差率≤5%；采购合规率100%；供应商评估覆盖率100%",
      personalMotivation: "不愿承担项目超预算后被问责的风险；希望所有IT采购采用'总包价'模式而非人天计价，降低审计风险",
      attitudeToUs: "认为AI项目投入大、周期长、效果不确定，倾向于先观望而非率先投入。担心项目超预算后被问责",
      attitudeToCompetitor: "对华为云的标准化定价模式有好感（明码标价、便于审计）；对我方人天计价模式有顾虑",
      engagement: 4, influence: 7, support: 2,
      compositeScore: zjg.compositeScore, gradeLevel: zjg.gradeLevel, confidence: "中",
      coreConcerns: "① 项目总预算超过2000万，审批难度大；② AI项目没有行业定价标准，担心供应商虚报；③ 担心项目周期失控，变成'无底洞'",
      leverage: "① 提供同行业AI项目案例的ROI数据；② 提出'分期支付、按里程碑验收'的付款方案；③ 承诺项目交付周期写入合同并设置延期罚则",
    },
    historyWithUs: "只见过1次（立项讨论会），目前持反对态度，是项目推进的最大阻力点。",
    historyWithCompetitor: "与多家IT供应商有采购合作经验，对华为云的商务条款比较认可（标准合同、价格透明）",
    behaviors: [
      { observation: "第一次立项讨论会全程沉默，最后问'投资回报周期多久？谁来验收？'", interpretation: "核心关注点是风险可控、责任清晰", suggestedAction: "准备详细的财务测算模型，明确每期交付物和验收标准" },
    ],
    stanceLog: [
      { date: "2026-07-02", from: "观望", to: "反对", reason: "立项讨论会后对预算规模和ROI测算不满意" },
    ],
  },
  {
    id: "sc-4", name: "张明辉", position: "集团科技部主任", department: "科技部",
    reportsTo: "集团副总裁", contactInfo: "zhangminghui@cnpc.com.cn",
    roleType: "coach_supporter", decisionPower: "影响者",
    background: {
      education: "中国科学院地质学博士",
      previousCompanies: "中石油工作18年，一直从事科技管理和技术战略规划",
      personality: "学术型管理者，视野开阔，关注行业趋势和技术前瞻性。喜欢引用国际案例",
      communicationPreference: "行业报告、学术文章、国际对标案例。接受深度交流但不耐烦'商务套路'",
      relationships: "与信息化部王主任关系密切（10年+）；在集团决策层有影响力，经常参与技术投资的评审",
    },
    subjective: {
      stance: "支持",
      explicitKPI: "集团科技创新考核达标（国资委对央企有科技创新考核要求）；年度科技项目立项数≥5项",
      personalMotivation: "希望通过AI项目推动集团科技创新考核指标达成，产出能发表高水平论文或申报科技奖项的成果；巩固科技部在集团的战略地位",
      attitudeToUs: "积极支持但不出头，主要在幕后推动。认为'数字化不能只做信息化，要做智能化才是未来'",
      attitudeToCompetitor: "认为华为云偏重基础设施层，在油气行业AI应用方面缺乏深度；认可我方在勘探AI领域的专业性",
      engagement: 6, influence: 8, support: 7,
      compositeScore: zmh.compositeScore, gradeLevel: zmh.gradeLevel, confidence: "高",
      coreConcerns: "① 项目定位需要与集团'十四五科技规划'对齐；② 希望产出能发表高水平论文或申报科技奖项",
      leverage: "① 帮助将项目纳入集团科技专项，获得额外资金支持；② 在决策评审会上表态支持；③ 推荐参与国资委'央企数字化转型典型案例'评选",
    },
    historyWithUs: "见过2次，关系融洽。他是重要的内部推手，需要在正式评审时用好他的影响力。",
    historyWithCompetitor: "曾与石化盈科在ERP项目上有合作，对传统IT服务商的能力边界比较清楚，认为其缺乏AI创新能力",
    behaviors: [
      { observation: "私下给我们发了3篇国际石油公司AI应用的研究报告，说'你们参考一下国际做法'", interpretation: "真心想帮我们做好，但又不想越权指挥", suggestedAction: "方案中多引用国际对标案例，体现前瞻性" },
    ],
    stanceLog: [
      { date: "2026-05-20", from: "中立", to: "支持", reason: "看了国际对标案例后认为方向正确" },
    ],
  },
  {
    id: "sc-5", name: "陈晓燕", position: "勘探事业部副经理", department: "勘探开发研究院",
    reportsTo: "事业部总经理", contactInfo: "chenxiaoyan@cnpc.com.cn",
    roleType: "user", decisionPower: "信息提供",
    background: {
      education: "中国石油大学（华东）石油工程本科",
      previousCompanies: "中石油工作14年，一直在勘探一线，做过地质师、项目经理",
      personality: "实战派，直爽。认为'AI能帮我们找油就是好东西，不能就是花架子'",
      communicationPreference: "用业务语言沟通，反感技术术语。喜欢看实际效果而非听PPT",
      relationships: "与勘探一线团队关系紧密，是业务部门的'民间意见领袖'",
    },
    subjective: {
      stance: "中立",
      explicitKPI: "探井成功率年度目标62%；井位论证报告按时交付率100%",
      personalMotivation: "最关心的是AI能不能真的提高探井成功率，减轻一线工作量。曾被之前几个数字化项目'伤害'过——花了几百万，最后没人用",
      attitudeToUs: "'我不是不相信AI，我是被之前几个数字化项目搞怕了——花了几百万，最后没人用'。Demo演示后态度有所松动",
      attitudeToCompetitor: "对之前合作过的传统IT服务商（如石化盈科）评价不高，认为'不懂业务'；未接触过AI方向供应商",
      engagement: 5, influence: 5, support: 5,
      compositeScore: cxy.compositeScore, gradeLevel: cxy.gradeLevel, confidence: "中",
      coreConcerns: "① AI工具好不好用，学习成本高不高；② 系统稳定性和响应速度；③ 会不会增加额外工作量（'不要为了数字化而数字化'）",
      leverage: "① 请她参与POC测试，亲自体验效果；② 让一线用户为项目'站台'，最有说服力",
    },
    historyWithUs: "见过1次（Demo演示），建立了初步好感。需要持续用真实业务场景验证价值。",
    historyWithCompetitor: "之前参与过石化盈科实施的MES项目（2019年），体验不佳，认为'系统复杂、不接地气'",
    behaviors: [
      { observation: "Demo演示时反复要求'再跑一个实际井位的数据看看'", interpretation: "用真实案例验证AI能力，务实态度", suggestedAction: "准备更多本土油田的实际案例，不要只展示公开数据集的结果" },
      { observation: "会后主动加微信，发了一份他们目前手工做井位评价的模板", interpretation: "认可我们方向，希望我们了解他们的实际工作流程", suggestedAction: "基于她提供的模板，做一个AI辅助井位评价的原型对比" },
    ],
    stanceLog: [
      { date: "2026-07-01", from: "反对", to: "中立", reason: "Demo演示用真实数据跑出合理结果，开始相信技术可行性" },
    ],
  },
];

// ---- 话术库（扩展到五类角色全覆盖） ----
const talkScripts: TalkScript[] = [
  // 经济决策人
  { id: "ts-1", stakeholderCardId: "sc-1", roleType: "economic_decision_maker", scenario: "初次拜访",
    content: "王主任您好，我们团队专注于为大型能源企业提供AI转型服务。了解到贵司在勘探开发领域有丰富的数据积累，我们想探讨如何用AI技术将这些数据转化为实际的勘探效益提升。这是我们在XX油田做的一个类似案例，探井成功率提升了8个百分点。" },
  { id: "ts-2", stakeholderCardId: "sc-1", roleType: "economic_decision_maker", scenario: "方案汇报",
    content: "王主任，基于前几次交流，我们设计了三期实施规划。第一期聚焦勘探AI，投入500万，周期6个月，目标提升探井成功率5个百分点。这是我们做的详细ROI测算：以贵司年均钻探200口井计算，成功率提升5%意味着每年少打10口干井，直接节约钻井成本约2亿元。" },
  { id: "ts-3", stakeholderCardId: "sc-1", roleType: "economic_decision_maker", scenario: "应对价格质疑",
    content: "我们的价格反映的是长期价值和风险控制。相比低价方案，我们能确保项目成功率和长期可维护性，避免您重复投资。而且我们采用分期交付模式，首期仅需500万，您可以先验证效果再决定后续投入。" },
  // 技术评估人
  { id: "ts-4", stakeholderCardId: "sc-2", roleType: "technical_evaluator", scenario: "技术交流",
    content: "李工，这是我们完整的技术架构白皮书。关于您关心的兼容性问题，我们的平台基于微服务架构，通过标准API与现有SAP系统对接，不需要推倒重建。数据层我们支持主流数据库，不会造成数据搬迁风险。这是我们在另一个央企客户的实际部署架构图。" },
  { id: "ts-5", stakeholderCardId: "sc-2", roleType: "technical_evaluator", scenario: "应对技术质疑",
    content: "您提到的AI模型可解释性问题，我们通过XAI（可解释AI）模块解决。每次模型推理都会输出关键特征贡献度，让您的团队能够理解决策依据。这是我们XAI模块的技术白皮书，可以安排技术专家给您做详细演示。" },
  // 采购/财务
  { id: "ts-6", stakeholderCardId: "sc-3", roleType: "procurement_finance", scenario: "预算讨论",
    content: "赵总，理解您对预算和ROI的关切。我们采用'分期交付、按里程碑验收'的合作模式，首期仅需500万，每期结束经验收通过才启动下一期。同时我们在合同中承诺交付周期和核心指标（如探井成功率提升5%），未达标不收取尾款。这里有3个同行业AI项目的实际ROI案例供参考。" },
  { id: "ts-7", stakeholderCardId: "sc-3", roleType: "procurement_finance", scenario: "应对压价",
    content: "我们理解您对成本的控制要求。我们的方案已是最优配置，如果再压缩可能影响关键功能交付。我们可以探讨分阶段实施，首期投入降低到XX万，先覆盖最核心的勘探AI场景，用首期效果来验证后续投入的必要性。" },
  // 教练/支持者
  { id: "ts-8", stakeholderCardId: "sc-4", roleType: "coach_supporter", scenario: "请求情报",
    content: "张主任，非常感谢您上次分享的国际案例，对我们的方案优化帮助很大。您觉得目前决策链上谁是最需要争取的？赵总那边对我们的方案主要疑虑是什么？我们好提前准备针对性的材料。" },
  // 使用者
  { id: "ts-9", stakeholderCardId: "sc-5", roleType: "user", scenario: "痛点挖掘",
    content: "陈经理，您之前提到现在手工做井位评价很耗时，能具体说说哪些步骤最让您头疼吗？我们希望把AI工具做到'上手即用'，不需要额外培训。如果方便的话，我们可以基于您上次分享的模板，先做一版AI辅助原型让您试用。" },
];

// ---- 知识库：五类角色识别特征 ----
const roleRecognition: RoleRecognition[] = [
  {
    roleType: "economic_decision_maker",
    bodyLanguage: "坐姿放松但有控制力，眼神直接，手势开放；较少做笔记，更多倾听后提问；时间观念强，常看表或手机",
    speechPattern: "关注'投资回报''战略意义''风险控制'；喜欢问'为什么是现在''和竞争对手比怎么样'；话少但问题尖锐，直击核心",
    typicalResponse: "'这个项目能给我带来多少收益？''你们做过类似的案例吗？''价格不是问题，关键是价值'",
    identificationSignal: "主动询问预算和决策流程；要求提供高层简报而非技术细节；介绍时强调'我最后拍板'",
  },
  {
    roleType: "technical_evaluator",
    bodyLanguage: "身体前倾，专注细节；频繁查看资料或屏幕；皱眉思考时手指敲桌面",
    speechPattern: "关注'架构''接口''性能''安全'；喜欢问'怎么实现的''数据怎么流转'；喜欢用专业术语，质疑技术细节",
    typicalResponse: "'这个方案和现有系统怎么集成？''数据安全怎么保障？''有没有做过压力测试？'",
    identificationSignal: "主动要求看架构图、API文档；询问技术团队规模和能力；要求提供POC环境",
  },
  {
    roleType: "user",
    bodyLanguage: "姿态相对放松，但提到现有工作时常有抱怨表情（撇嘴、摇头）；操作现有系统时流露出不耐烦",
    speechPattern: "关注'好不好用''能不能少干活''会不会更麻烦'；喜欢吐槽现有系统痛点；具体描述日常工作中的困难",
    typicalResponse: "'现在这个系统太慢了，每次都要等半天''能不能自动生成报表？''我们部门人少，希望别太复杂'",
    identificationSignal: "主动展示现有工作流程中的痛点；询问操作步骤和上手难度；关心培训和支持服务",
  },
  {
    roleType: "coach_supporter",
    bodyLanguage: "眼神交流频繁，姿态开放；愿意分享额外信息（如压低声音）；主动介绍内部关系",
    speechPattern: "主动提供内部信息（决策流程、竞品动态、关键人物性格）；给出建议'你们最好先搞定X总'；愿意引荐其他角色",
    typicalResponse: "'我跟你说，真正说了算的是X总''你们上次的方案，Y总觉得不错，但担心Z问题''我可以帮你们约一下X总'",
    identificationSignal: "主动透露内部政治信息；愿意在非正式场合（如饭局、咖啡）深入交流；对你方表现出个人好感",
  },
  {
    roleType: "procurement_finance",
    bodyLanguage: "姿态正式，注重流程；频繁查看文件或表格；表情谨慎，少情感流露",
    speechPattern: "关注'合规''流程''预算''付款条件'；喜欢问'有没有走完审批''价格构成是什么'；喜欢用条款和数字",
    typicalResponse: "'这个价格包含哪些服务？''付款方式是怎样的？''你们有没有入围我们的供应商库？'",
    identificationSignal: "主动介绍采购流程和时间节点；询问资质和案例证明；关注合同条款和合规文件",
  },
];

// ---- 知识库：行为分析速查表 ----
const behaviorQuickRef: BehaviorQuickRef[] = [
  { observation: "主动询问方案细节，做笔记", interpretation: "有真实兴趣，可能成为支持者", suggestedAction: "提供详细资料，安排深度交流" },
  { observation: "频繁看表，回应简短", interpretation: "时间紧张或不感兴趣", suggestedAction: "缩短沟通，尝试了解真实原因" },
  { observation: "提到'以前和XX合作过'", interpretation: "有历史合作关系，可能倾向竞品", suggestedAction: "了解历史合作满意度，寻找差异化优势" },
  { observation: "主动介绍内部关系和决策流程", interpretation: "可能成为教练", suggestedAction: "建立信任，请求进一步帮助" },
  { observation: "质疑方案中的技术细节", interpretation: "技术评估者正常反应", suggestedAction: "认真回应，展现专业度" },
  { observation: "质疑方案价值，认为价格高", interpretation: "可能是反对者或财务角色", suggestedAction: "提供ROI分析，或寻求更高层支持" },
  { observation: "愿意在非正式场合（如饭局）继续聊", interpretation: "信任度较高，可能成为支持者", suggestedAction: "加强关系，了解个人诉求" },
  { observation: "拒绝见面，只愿意邮件沟通", interpretation: "可能反对，或非常忙", suggestedAction: "尝试通过其他角色引荐，或提供更有吸引力的价值点" },
];

// ============================================================
// 组件
// ============================================================

const roleTypeLabels: Record<RoleType, string> = {
  economic_decision_maker: "经济决策人",
  technical_evaluator: "技术评估人",
  user: "终端用户",
  coach_supporter: "教练/支持者",
  procurement_finance: "采购/财务",
};

const roleTypeColor: Record<RoleType, string> = {
  economic_decision_maker: "var(--accent)",
  technical_evaluator: "var(--info)",
  user: "var(--warn)",
  coach_supporter: "var(--success)",
  procurement_finance: "var(--danger)",
};

const stanceDotColor = (s: StanceLevel) => {
  if (s === "支持") return "var(--success)";
  if (s === "反对") return "var(--danger)";
  if (s === "中立") return "var(--warn)";
  return "var(--ink-3)";
};

const gradeLevelColor = (g: GradeLevel) => {
  if (g === "Champion") return "var(--success)";
  if (g === "倾向我方") return "var(--accent)";
  if (g === "中立") return "var(--warn)";
  return "var(--danger)";
};

export default function MarketingMapPage() {
  const [selectedProject, setSelectedProject] = useState(MOCK_PROJECTS[0].id);
  const [view, setView] = useState("cards");
  const [selectedCard, setSelectedCard] = useState<StakeholderCard>(stakeholderCards[0]);
  const [detailTab, setDetailTab] = useState("objective");

  const views = [
    ["org", "组织架构"],
    ["decision", "决策链"],
    ["matrix", "立场矩阵"],
    ["timeline", "采购时间线"],
    ["cards", "角色卡"],
    ["knowledge", "知识库"],
  ] as const;

  const supportCount = stakeholderCards.filter(c => c.subjective.stance === "支持").length;
  const championCount = stakeholderCards.filter(c => c.subjective.gradeLevel === "Champion").length;

  // 话术按角色类型分组
  const scriptsByRole = useMemo(() => {
    const map: Record<string, TalkScript[]> = {};
    for (const ts of talkScripts) {
      if (!map[ts.roleType]) map[ts.roleType] = [];
      map[ts.roleType].push(ts);
    }
    return map;
  }, []);

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
        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>角色总数: <b style={{ color: "var(--ink)" }}>{stakeholderCards.length}</b></span>
        <span style={{ fontSize: 12, color: "var(--success)" }}>Champion: <b>{championCount}</b></span>
        <span style={{ fontSize: 12, color: "var(--accent)" }}>支持: <b>{supportCount}</b></span>
        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>最近更新: 2026-07-05</span>
      </div>

      {/* 视图 Tab（新增：知识库） */}
      <div style={{ padding: "0 20px", borderBottom: "1px solid var(--line)", background: "var(--bg)", display: "flex", gap: 0, flexShrink: 0 }}>
        {views.map(([key, label]) => (
          <button key={key} onClick={() => setView(key)}
            style={{
              padding: "10px 16px", background: "transparent", border: "none",
              borderBottom: view === key ? "2px solid var(--accent)" : "2px solid transparent",
              color: view === key ? "var(--accent)" : "var(--ink-2)",
              fontSize: 13, fontWeight: view === key ? 600 : 400,
              cursor: "pointer", fontFamily: "inherit", transition: "color 120ms, border-color 120ms",
            }}>
            {label}
          </button>
        ))}
      </div>

      {/* 主内容 */}
      <div style={{ flex: 1, overflow: "auto", padding: 20, display: "flex", gap: 20 }}>
        {/* 左侧角色列表 */}
        <Card style={{ width: 230, padding: 0, flexShrink: 0, overflow: "auto", display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--line)", fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: 0.6 }}>
            角色列表
          </div>
          <div style={{ flex: 1, overflow: "auto" }}>
            {stakeholderCards.map(c => (
              <button key={c.id} onClick={() => { setSelectedCard(c); setView("cards"); }}
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
                  border: "none", textAlign: "left",
                  borderLeft: selectedCard.id === c.id ? "3px solid var(--accent)" : "3px solid transparent",
                  background: selectedCard.id === c.id ? "var(--bg-2)" : "transparent",
                  cursor: "pointer", fontFamily: "inherit", fontSize: 13,
                  transition: "background 120ms",
                }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 14, fontWeight: 700, color: "#FFFCF5",
                  background: roleTypeColor[c.roleType],
                  flexShrink: 0,
                }}>
                  {c.name[0]}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</div>
                  <div style={{ fontSize: 11, color: "var(--ink-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.position}</div>
                </div>
                <span style={{ width: 6, height: 6, borderRadius: 999, background: stanceDotColor(c.subjective.stance), flexShrink: 0 }} />
              </button>
            ))}
          </div>
        </Card>

        {/* 主面板 */}
        {view === "cards" ? (
          <Card style={{ flex: 1, padding: 0, overflow: "auto", display: "flex", flexDirection: "column" }}>
            {/* 角色卡头部 */}
            <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "center", gap: 16 }}>
              <div style={{
                width: 44, height: 44, borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 20, fontWeight: 700, color: "#FFFCF5",
                background: roleTypeColor[selectedCard.roleType],
                flexShrink: 0,
              }}>
                {selectedCard.name[0]}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 16, fontWeight: 600, fontFamily: "var(--serif)" }}>{selectedCard.name}</div>
                <div style={{ fontSize: 12, color: "var(--ink-2)" }}>{selectedCard.position} · {selectedCard.department} · 汇报: {selectedCard.reportsTo}</div>
                {selectedCard.contactInfo && <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>📧 {selectedCard.contactInfo}</div>}
              </div>
              <div style={{ display: "flex", gap: 6, flexDirection: "column", alignItems: "flex-end" }}>
                <div style={{ display: "flex", gap: 6 }}>
                  <Tag tone="accent">{roleTypeLabels[selectedCard.roleType]}</Tag>
                  <Tag tone="info">{selectedCard.decisionPower}</Tag>
                </div>
                <Tag tone={selectedCard.subjective.gradeLevel === "Champion" ? "success" : selectedCard.subjective.gradeLevel === "倾向我方" ? "accent" : selectedCard.subjective.gradeLevel === "中立" ? "warn" : "danger"}>
                  {selectedCard.subjective.gradeLevel} · 置信{selectedCard.subjective.confidence}
                </Tag>
              </div>
            </div>

            {/* 详情 Tab（新增：竞品历史） */}
            <div style={{ display: "flex", borderBottom: "1px solid var(--line)", padding: "0 16px" }}>
              {(["objective", "subjective", "behavior", "history", "talkscript"] as const).map(tab => (
                <button key={tab} onClick={() => setDetailTab(tab)}
                  style={{
                    padding: "10px 14px", background: "transparent", border: "none",
                    borderBottom: detailTab === tab ? "2px solid var(--accent)" : "2px solid transparent",
                    color: detailTab === tab ? "var(--accent)" : "var(--ink-2)",
                    fontSize: 12.5, fontWeight: detailTab === tab ? 600 : 400,
                    cursor: "pointer", fontFamily: "inherit", transition: "color 120ms",
                  }}>
                  {tab === "objective" ? "客观信息" : tab === "subjective" ? "主观分析" : tab === "behavior" ? "行为分析" : tab === "history" ? "态度历史" : "话术库"}
                </button>
              ))}
            </div>

            {/* Tab 内容 */}
            <div style={{ flex: 1, overflow: "auto", padding: 20 }}>
              {detailTab === "objective" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14, fontSize: 13 }}>
                  <Section title="教育背景" content={selectedCard.background.education} />
                  <Section title="过往经历" content={selectedCard.background.previousCompanies} />
                  <Section title="性格特征" content={selectedCard.background.personality} />
                  <Section title="沟通偏好" content={selectedCard.background.communicationPreference} />
                  <Section title="人际关系" content={selectedCard.background.relationships} />
                  <div style={{ borderTop: "1px solid var(--line)", paddingTop: 8 }}>
                    <Section title="与我方历史合作" content={selectedCard.historyWithUs} />
                  </div>
                  <Section title="与竞品历史合作" content={selectedCard.historyWithCompetitor} highlight />
                </div>
              )}
              {detailTab === "subjective" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14, fontSize: 13 }}>
                  {/* 三维度评分 + 综合评分 + 等级 */}
                  <div style={{ display: "flex", gap: 12, marginBottom: 4 }}>
                    {[
                      ["参与度", selectedCard.subjective.engagement, "var(--info)", 0.3],
                      ["影响力", selectedCard.subjective.influence, "var(--accent)", 0.4],
                      ["支持度", selectedCard.subjective.support, selectedCard.subjective.support >= 7 ? "var(--success)" : selectedCard.subjective.support >= 4 ? "var(--warn)" : "var(--danger)", 0.3],
                    ].map(([label, value, color, weight]) => (
                      <div key={String(label)} style={{
                        flex: 1, textAlign: "center", padding: "12px 8px",
                        background: "var(--bg-2)", borderRadius: 10, border: "1px solid var(--line)",
                      }}>
                        <div style={{ fontSize: 22, fontWeight: 700, color: String(color) }}>{String(value)}<span style={{ fontSize: 11, color: "var(--ink-3)" }}>/10</span></div>
                        <div style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 2 }}>{String(label)}（权重{String(weight)}）</div>
                      </div>
                    ))}
                    <div style={{
                      flex: 1, textAlign: "center", padding: "12px 8px",
                      background: "var(--accent-soft)", borderRadius: 10, border: "1px solid var(--accent)",
                    }}>
                      <div style={{ fontSize: 22, fontWeight: 700, color: "var(--accent)" }}>{selectedCard.subjective.compositeScore}<span style={{ fontSize: 11, color: "var(--ink-3)" }}>/10</span></div>
                      <div style={{ fontSize: 10, color: "var(--accent)", marginTop: 2, fontWeight: 600 }}>综合评分</div>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: "var(--bg-2)", borderRadius: 8 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)" }}>立场</span>
                    <span style={{
                      padding: "3px 12px", borderRadius: 999, fontSize: 13, fontWeight: 600,
                      background: stanceDotColor(selectedCard.subjective.stance) + "22",
                      color: stanceDotColor(selectedCard.subjective.stance),
                    }}>{selectedCard.subjective.stance}</span>
                    <span style={{ fontSize: 11, color: "var(--ink-3)" }}>|</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)" }}>等级</span>
                    <span style={{
                      padding: "3px 12px", borderRadius: 999, fontSize: 13, fontWeight: 600,
                      background: gradeLevelColor(selectedCard.subjective.gradeLevel) + "22",
                      color: gradeLevelColor(selectedCard.subjective.gradeLevel),
                    }}>{selectedCard.subjective.gradeLevel}</span>
                  </div>
                  <Section title="显性KPI（公开考核指标）" content={selectedCard.subjective.explicitKPI} />
                  <Section title="隐性个人诉求" content={selectedCard.subjective.personalMotivation} />
                  <Section title="对我方方案的态度" content={selectedCard.subjective.attitudeToUs} />
                  <Section title="对竞品的态度" content={selectedCard.subjective.attitudeToCompetitor} />
                  <Section title="核心顾虑" content={selectedCard.subjective.coreConcerns} highlight />
                  <Section title="影响杠杆" content={selectedCard.subjective.leverage} />
                </div>
              )}
              {detailTab === "behavior" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 4 }}>行为分析矩阵</div>
                  {selectedCard.behaviors.map((b, i) => (
                    <div key={i} style={{ padding: 14, background: "var(--bg-2)", borderRadius: 10, border: "1px solid var(--line)", fontSize: 13 }}>
                      <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
                        <span style={{ fontWeight: 600, color: "var(--ink)", flexShrink: 0, width: 60 }}>🔍 观察</span>
                        <span style={{ color: "var(--ink-2)" }}>{b.observation}</span>
                      </div>
                      <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
                        <span style={{ fontWeight: 600, color: "var(--info)", flexShrink: 0, width: 60 }}>🧠 解读</span>
                        <span style={{ color: "var(--ink-2)" }}>{b.interpretation}</span>
                      </div>
                      <div style={{ display: "flex", gap: 10, borderTop: "1px solid var(--line)", paddingTop: 10 }}>
                        <span style={{ fontWeight: 600, color: "var(--accent)", flexShrink: 0, width: 60 }}>💡 建议</span>
                        <span style={{ color: "var(--ink)" }}>{b.suggestedAction}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {detailTab === "history" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 12 }}>态度变化日志</div>
                  {selectedCard.stanceLog.map((log, i) => (
                    <div key={i} style={{
                      display: "flex", alignItems: "flex-start", gap: 12, padding: "10px 0", borderLeft: "2px solid var(--line)",
                      marginLeft: 8, paddingLeft: 16, position: "relative",
                    }}>
                      <div style={{
                        position: "absolute", left: -5, top: 14, width: 8, height: 8,
                        borderRadius: 999, background: "var(--accent)",
                      }} />
                      <div style={{ fontSize: 12, color: "var(--ink-3)", flexShrink: 0, width: 80 }}>{log.date}</div>
                      <div style={{ flex: 1, fontSize: 13 }}>
                        <span style={{
                          padding: "1px 8px", borderRadius: 999, fontSize: 11, fontWeight: 500,
                          background: stanceDotColor(log.from) + "22", color: stanceDotColor(log.from),
                        }}>{log.from}</span>
                        <span style={{ margin: "0 6px", color: "var(--ink-4)" }}>→</span>
                        <span style={{
                          padding: "1px 8px", borderRadius: 999, fontSize: 11, fontWeight: 500,
                          background: stanceDotColor(log.to) + "22", color: stanceDotColor(log.to),
                        }}>{log.to}</span>
                        <div style={{ color: "var(--ink-2)", marginTop: 4 }}>{log.reason}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {detailTab === "talkscript" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase" }}>话术库 — {selectedCard.name}（{roleTypeLabels[selectedCard.roleType]}）</div>
                  {talkScripts.filter(ts => ts.stakeholderCardId === selectedCard.id).map(ts => (
                    <div key={ts.id} style={{
                      padding: 14, background: "var(--bg-2)", borderRadius: 10, border: "1px solid var(--line)",
                    }}>
                      <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
                        <Tag tone="accent">{roleTypeLabels[ts.roleType]}</Tag>
                        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>场景: {ts.scenario}</span>
                      </div>
                      <div style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.7, fontStyle: "italic", padding: "10px 14px", background: "var(--surface)", borderRadius: 8, border: "1px solid var(--line)" }}>
                        "{ts.content}"
                      </div>
                    </div>
                  ))}
                  {talkScripts.filter(ts => ts.stakeholderCardId === selectedCard.id).length === 0 && (
                    <div style={{ fontSize: 13, color: "var(--ink-3)", textAlign: "center", padding: 40 }}>暂无话术，请通过对话生成</div>
                  )}
                  {/* 同类型角色的通用话术模板 */}
                  <div style={{ borderTop: "1px dashed var(--line)", paddingTop: 12 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", marginBottom: 8 }}>
                      📋 同类型角色通用话术模板
                    </div>
                    {(scriptsByRole[selectedCard.roleType] || []).filter(ts => ts.stakeholderCardId !== selectedCard.id).length > 0 ? (
                      (scriptsByRole[selectedCard.roleType] || []).filter(ts => ts.stakeholderCardId !== selectedCard.id).map(ts => (
                        <div key={ts.id} style={{
                          padding: 10, marginBottom: 6, background: "var(--bg)", borderRadius: 6, border: "1px solid var(--line)",
                        }}>
                          <div style={{ fontSize: 11, color: "var(--ink-3)", marginBottom: 4 }}>场景: {ts.scenario}</div>
                          <div style={{ fontSize: 12, color: "var(--ink-2)", fontStyle: "italic" }}>"{ts.content.substring(0, 100)}..."</div>
                        </div>
                      ))
                    ) : (
                      <div style={{ fontSize: 12, color: "var(--ink-3)" }}>暂无同类型角色的额外话术模板</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </Card>
        ) : view === "org" ? (
          <Card style={{ flex: 1, padding: 20 }}>
            <div style={{ fontSize: 13, color: "var(--ink-3)", marginBottom: 16 }}>组织架构图 — 标注汇报关系与关键岗位</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 13, maxWidth: 500 }}>
              <OrgNode label="集团副总裁" type="top" />
              <div style={{ marginLeft: 40, borderLeft: "2px solid var(--line)", paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6 }}>
                <OrgNode label="王国强（信息化部主任）" type="decision" active />
                <div style={{ marginLeft: 30, borderLeft: "2px solid var(--line)", paddingLeft: 20, display: "flex", flexDirection: "column", gap: 4 }}>
                  <OrgNode label="李明远（技术负责人）" type="eval" />
                  <OrgNode label="IT运维团队 (3人)" type="team" />
                </div>
                <OrgNode label="赵建国（财务部副总）" type="finance" />
                <OrgNode label="张明辉（科技部主任）" type="coach" />
                <OrgNode label="陈晓燕（勘探事业部副经理）" type="user" />
              </div>
            </div>
          </Card>
        ) : view === "decision" ? (
          <Card style={{ flex: 1, padding: 20, overflow: "auto" }}>
            <div style={{ fontSize: 13, color: "var(--ink-3)", marginBottom: 16 }}>决策链角色表 — 按影响力排序</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "var(--bg-2)", borderBottom: "2px solid var(--line)" }}>
                  {["角色类型", "姓名", "部门", "决策权", "影响力", "综合评分", "等级", "立场"].map(h => (
                    <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "var(--ink-3)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...stakeholderCards].sort((a, b) => b.subjective.influence - a.subjective.influence).map(c => (
                  <tr key={c.id} style={{ borderBottom: "1px solid var(--line)", cursor: "pointer" }}
                    onClick={() => { setSelectedCard(c); setView("cards"); }}>
                    <td style={{ padding: "10px 14px" }}><Tag tone="accent">{roleTypeLabels[c.roleType]}</Tag></td>
                    <td style={{ padding: "10px 14px", fontWeight: 500 }}>{c.name}</td>
                    <td style={{ padding: "10px 14px", color: "var(--ink-2)" }}>{c.department}</td>
                    <td style={{ padding: "10px 14px", color: "var(--ink-2)", fontSize: 12 }}>{c.decisionPower}</td>
                    <td style={{ padding: "10px 14px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div style={{ width: 60, height: 4, background: "var(--bg-3)", borderRadius: 2, overflow: "hidden" }}>
                          <div style={{ width: `${c.subjective.influence * 10}%`, height: "100%", background: "var(--accent)", borderRadius: 2 }} />
                        </div>
                        <span style={{ fontSize: 11, fontWeight: 600 }}>{c.subjective.influence}/10</span>
                      </div>
                    </td>
                    <td style={{ padding: "10px 14px" }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: gradeLevelColor(c.subjective.gradeLevel) }}>{c.subjective.compositeScore}分</span>
                    </td>
                    <td style={{ padding: "10px 14px" }}>
                      <span style={{
                        padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 500,
                        background: gradeLevelColor(c.subjective.gradeLevel) + "22",
                        color: gradeLevelColor(c.subjective.gradeLevel),
                      }}>{c.subjective.gradeLevel}</span>
                    </td>
                    <td style={{ padding: "10px 14px" }}>
                      <span style={{ fontSize: 12, fontWeight: 500, color: stanceDotColor(c.subjective.stance) }}>{c.subjective.stance}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        ) : view === "matrix" ? (
          <Card style={{ flex: 1, padding: 20 }}>
            <div style={{ fontSize: 13, color: "var(--ink-3)", marginBottom: 16 }}>角色-立场矩阵 — 横轴立场 × 纵轴影响力</div>
            <div style={{ position: "relative", width: 500, height: 300, margin: "20px auto", borderLeft: "2px solid var(--line)", borderBottom: "2px solid var(--line)" }}>
              <div style={{ position: "absolute", left: -30, top: -10, fontSize: 11, color: "var(--ink-3)" }}>影响力</div>
              <div style={{ position: "absolute", left: -15, top: 0, fontSize: 10, color: "var(--ink-4)" }}>10</div>
              <div style={{ position: "absolute", left: -15, top: 140, fontSize: 10, color: "var(--ink-4)" }}>5</div>
              <div style={{ position: "absolute", left: -15, top: 285, fontSize: 10, color: "var(--ink-4)" }}>0</div>
              <div style={{ position: "absolute", bottom: -22, left: 100, fontSize: 10, color: "var(--danger)" }}>反对</div>
              <div style={{ position: "absolute", bottom: -22, left: 230, fontSize: 10, color: "var(--warn)" }}>中立</div>
              <div style={{ position: "absolute", bottom: -22, left: 360, fontSize: 10, color: "var(--success)" }}>支持</div>
              {stakeholderCards.map(c => {
                const x = c.subjective.stance === "反对" ? 15 : c.subjective.stance === "观望" ? 35 : c.subjective.stance === "中立" ? 55 : 85;
                const y = 100 - c.subjective.influence * 10;
                const size = 24 + c.subjective.engagement * 2;
                return (
                  <div key={c.id}
                    onClick={() => { setSelectedCard(c); setView("cards"); }}
                    title={`${c.name}: 影响力${c.subjective.influence} 支持度${c.subjective.support} 综合${c.subjective.compositeScore}分`}
                    style={{
                      position: "absolute", left: `calc(${x}% - ${size / 2}px)`, top: `calc(${y}% - ${size / 2}px)`,
                      width: size, height: size, borderRadius: 999, cursor: "pointer",
                      background: stanceDotColor(c.subjective.stance),
                      opacity: 0.8, border: "2px solid var(--bg)",
                      boxShadow: "var(--shadow-sm)", display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 9, fontWeight: 700, color: "#FFFCF5",
                      transition: "transform 120ms",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.transform = "scale(1.2)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.transform = "scale(1)"; }}
                  >
                    {c.name[0]}
                  </div>
                );
              })}
            </div>
          </Card>
        ) : view === "timeline" ? (
          <Card style={{ flex: 1, padding: 20 }}>
            <div style={{ fontSize: 13, color: "var(--ink-3)", marginBottom: 16 }}>采购流程时间线 — 五阶段模板</div>
            {["需求识别", "方案评估", "供应商筛选", "商务谈判", "合同签署"].map((phase, i) => (
              <div key={phase} style={{ display: "flex", gap: 16, marginBottom: 4 }}>
                <div style={{ width: 80, textAlign: "right", flexShrink: 0 }}>
                  <span style={{
                    padding: "2px 8px", borderRadius: 999, fontSize: 10, fontWeight: 600,
                    background: i <= 1 ? "var(--success-soft)" : "var(--bg-3)",
                    color: i <= 1 ? "var(--success)" : "var(--ink-3)",
                  }}>{i <= 1 ? "✅ 已完成" : "⏳ 待开始"}</span>
                </div>
                <div style={{
                  borderLeft: "2px solid " + (i <= 1 ? "var(--success)" : "var(--line)"),
                  paddingLeft: 16, paddingBottom: 20, position: "relative",
                }}>
                  <div style={{
                    position: "absolute", left: -5, top: 0, width: 8, height: 8,
                    borderRadius: 999, background: i <= 1 ? "var(--success)" : "var(--line)",
                  }} />
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{phase}</div>
                  <div style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 4 }}>
                    {i === 0 ? "已完成：识别AI中台建设需求，形成内部立项报告" :
                     i === 1 ? "进行中：评估3家供应商方案（我方+华为云+阿里云）" :
                     i === 2 ? "计划：2026-08 完成供应商筛选和POC测试" :
                     i === 3 ? "计划：2026-09 商务谈判与合同条款确认" :
                     "计划：2026-10 签署合同，正式启动项目"}
                  </div>
                </div>
              </div>
            ))}
          </Card>
        ) : view === "knowledge" ? (
          // 知识库视图（新增）
          <Card style={{ flex: 1, padding: 20, overflow: "auto" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
              {/* 五类角色速查表 */}
              <div>
                <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)", marginBottom: 12 }}>
                  🎯 五类角色识别速查表
                </div>
                <div style={{ overflow: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr style={{ background: "var(--bg-2)", borderBottom: "2px solid var(--line)" }}>
                        {["角色类型", "典型职位", "核心关注", "身体语言", "话语特征", "识别信号"].map(h => (
                          <th key={h} style={{ padding: "8px 10px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "var(--ink-3)", whiteSpace: "nowrap" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {roleRecognition.map(rr => (
                        <tr key={rr.roleType} style={{ borderBottom: "1px solid var(--line)" }}>
                          <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>
                            <span style={{
                              padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 500,
                              background: roleTypeColor[rr.roleType] + "22",
                              color: roleTypeColor[rr.roleType],
                            }}>{roleTypeLabels[rr.roleType]}</span>
                          </td>
                          <td style={{ padding: "8px 10px", color: "var(--ink-2)", fontSize: 11, whiteSpace: "nowrap" }}>
                            {rr.roleType === "economic_decision_maker" ? "总经理、董事长、CEO" :
                             rr.roleType === "technical_evaluator" ? "CTO、技术总监、架构师" :
                             rr.roleType === "user" ? "业务经理、运维工程师" :
                             rr.roleType === "coach_supporter" ? "任何角色（需有影响力）" :
                             "采购经理、财务总监"}
                          </td>
                          <td style={{ padding: "8px 10px", color: "var(--ink-2)", fontSize: 11, whiteSpace: "nowrap" }}>
                            {rr.roleType === "economic_decision_maker" ? "ROI、战略匹配、风险" :
                             rr.roleType === "technical_evaluator" ? "架构、安全、集成性" :
                             rr.roleType === "user" ? "易用性、效率提升" :
                             rr.roleType === "coach_supporter" ? "个人利益、信任关系" :
                             "合规、价格、付款条件"}
                          </td>
                          <td style={{ padding: "8px 10px", color: "var(--ink-3)", fontSize: 11, maxWidth: 180 }}>{rr.bodyLanguage}</td>
                          <td style={{ padding: "8px 10px", color: "var(--ink-3)", fontSize: 11, maxWidth: 220 }}>{rr.speechPattern}</td>
                          <td style={{ padding: "8px 10px", color: "var(--accent)", fontSize: 11, maxWidth: 180 }}>{rr.identificationSignal}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* 行为分析速查表 */}
              <div style={{ borderTop: "1px solid var(--line)", paddingTop: 20 }}>
                <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)", marginBottom: 12 }}>
                  🔍 行为分析速查表（观察→解读→动作）
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {behaviorQuickRef.map((bq, i) => (
                    <div key={i} style={{ display: "flex", gap: 12, padding: "10px 14px", background: "var(--bg-2)", borderRadius: 8, border: "1px solid var(--line)", fontSize: 12, alignItems: "flex-start" }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: "var(--ink-3)", marginBottom: 3 }}>👁️ 观察行为</div>
                        <div style={{ color: "var(--ink)" }}>{bq.observation}</div>
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: "var(--info)", marginBottom: 3 }}>🧠 可能解读</div>
                        <div style={{ color: "var(--ink-2)" }}>{bq.interpretation}</div>
                      </div>
                      <div style={{ flex: 1.2 }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: "var(--accent)", marginBottom: 3 }}>💡 下一步动作</div>
                        <div style={{ color: "var(--ink)" }}>{bq.suggestedAction}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 新人培养流程 */}
              <div style={{ borderTop: "1px solid var(--line)", paddingTop: 20 }}>
                <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)", marginBottom: 12 }}>
                  🌱 新人培养流程（4阶段）
                </div>
                <div style={{ display: "flex", gap: 0 }}>
                  {[
                    ["📚 理论学习", "1周", "阅读角色画像库和话术模板库，掌握五类角色基本特征"],
                    ["🎭 模拟演练", "2天", "基于真实客户案例进行角色扮演（红蓝军对抗），由资深顾问点评"],
                    ["👣 跟岗实践", "2周", "跟随资深顾问拜访客户，观察实际沟通，记录行为分析"],
                    ["🚀 独立拜访", "持续", "独立拜访低难度客户，提交拜访纪要和角色分析报告，导师复盘"],
                  ].map(([title, duration, desc], i) => (
                    <div key={i} style={{ flex: 1, textAlign: "center", position: "relative" }}>
                      {i > 0 && (
                        <div style={{ position: "absolute", left: -8, top: 24, color: "var(--ink-4)", fontSize: 16 }}>→</div>
                      )}
                      <div style={{
                        padding: "12px 10px", margin: "0 6px", background: "var(--bg-2)", borderRadius: 10,
                        border: `2px solid ${i === 0 ? "var(--info)" : i === 1 ? "var(--accent)" : i === 2 ? "var(--success)" : "var(--warn)"}`,
                      }}>
                        <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{title}</div>
                        <div style={{
                          padding: "2px 10px", borderRadius: 999, fontSize: 10, fontWeight: 600, display: "inline-block",
                          background: "var(--bg-3)", color: "var(--ink-2)", marginBottom: 8,
                        }}>{duration}</div>
                        <div style={{ fontSize: 11, color: "var(--ink-2)", lineHeight: 1.5, textAlign: "left" }}>{desc}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Card>
        ) : null}

        {/* 右侧关联面板 */}
        <Card style={{ width: 220, padding: 20, flexShrink: 0 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 12 }}>关联信息</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--ink-3)" }}>📎 关联 L3 场景</span>
              <b>3</b>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--ink-3)" }}>📝 关联拜访记录</span>
              <b>5</b>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--ink-3)" }}>💬 关联话术</span>
              <b>{talkScripts.length}</b>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--ink-3)" }}>🔗 关联证据</span>
              <b>28</b>
            </div>
          </div>
          <div style={{ marginTop: 20, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 8 }}>团队角色分布</div>
            {(["economic_decision_maker", "technical_evaluator", "user", "coach_supporter", "procurement_finance"] as RoleType[]).map(rt => {
              const count = stakeholderCards.filter(c => c.roleType === rt).length;
              return (
                <div key={rt} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, padding: "3px 0", color: "var(--ink-2)" }}>
                  <span>{roleTypeLabels[rt]}</span>
                  <b>{count}</b>
                </div>
              );
            })}
          </div>
          <div style={{ marginTop: 20, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 8 }}>评分分布</div>
            {(["Champion", "倾向我方", "中立", "反对"] as GradeLevel[]).map(g => {
              const count = stakeholderCards.filter(c => c.subjective.gradeLevel === g).length;
              return (
                <div key={g} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, padding: "3px 0", color: "var(--ink-2)" }}>
                  <span style={{ color: gradeLevelColor(g) }}>● {g}</span>
                  <b>{count}</b>
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </div>
  );
}

// 辅助组件
function Section({ title, content, highlight }: { title: string; content: string; highlight?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, color: highlight ? "var(--danger)" : "var(--ink-3)", marginBottom: 4 }}>{title}</div>
      <div style={{
        fontSize: 13, color: "var(--ink-2)", lineHeight: 1.65,
        ...(highlight ? { background: "var(--danger-soft)", padding: "8px 12px", borderRadius: 6 } : {}),
      }}>{content}</div>
    </div>
  );
}

function OrgNode({ label, type, active }: { label: string; type: string; active?: boolean }) {
  const colors: Record<string, string> = {
    top: "var(--ink)",
    decision: "var(--accent)",
    eval: "var(--info)",
    finance: "var(--danger)",
    coach: "var(--success)",
    user: "var(--warn)",
    team: "var(--ink-3)",
  };
  return (
    <div style={{
      padding: "8px 14px", borderRadius: 8, fontSize: 12,
      background: active ? "var(--accent-soft)" : "var(--bg-2)",
      border: `1px solid ${active ? "var(--accent)" : "var(--line)"}`,
      color: colors[type] || "var(--ink)",
      fontWeight: type === "top" ? 600 : 400,
    }}>
      {label}
    </div>
  );
}
