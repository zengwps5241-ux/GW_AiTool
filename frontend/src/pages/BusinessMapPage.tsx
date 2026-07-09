// 🧪 PROTOTYPE — 业务地图页面（V2.0 规格 2.3 节）
// 中石油数字化转型项目 模拟数据
// 已按 L1-L4 设计文档补全全部字段：前置分析、五维健康、本体抽取等
import { useState } from "react";
import { I } from "@/icons";
import { Card, Tag } from "@/components/ui";

// ============================================================
// 类型定义（对齐设计文档全部字段）
// ============================================================

/** 五维健康评分（L1/L2/L3 各有独立的观测指标） */
interface FiveDimHealth {
  L5_数字意识: { score: number; desc: string };
  L4_数字神经: { score: number; desc: string };
  L3_数字器官: { score: number; desc: string };
  L2_数字血液: { score: number; desc: string };
  L1_数字骨架: { score: number; desc: string };
}

/** 业务本体抽取（L3 核心字段，设计文档强调"先本体后AI"） */
interface OntologyExtraction {
  entities: string;   // 实体
  relations: string;  // 关系
  rules: string;      // 规则
  actions: string;    // 动作
}

/** 前置分析（L1 产业环境与战略定位，项目级别） */
interface PreAnalysis {
  industryValueChain: string;    // 行业价值链
  customerPosition: string;      // 客户行业地位
  industryTrends: string;        // 行业趋势与变化
  strategicPositioning: string;  // 客户战略定位
  digitalizationDrivers: string; // 数字化驱动力
}

interface MapNode {
  id: string;
  level: "L1" | "L2" | "L3" | "L4";
  name: string;
  parentId: string | null;
  mapType: "hypothesis" | "current";
  verificationStatus?: "未验证" | "成立" | "部分成立" | "推翻" | "待补充";
  confidenceLevel: "高" | "中" | "低";
  sourceType: "搜索采集" | "用户上传" | "行业模板" | "模型知识";

  // --- L1 fields (5要素) ---
  coreActivities?: string;
  capabilityChain?: string;
  itSystems?: string;
  organization?: string;
  fiveDimHealth?: FiveDimHealth;

  // --- L2 fields (8要素) ---
  domainType?: "业务域" | "职能域" | "共性技术域";
  domainGoal?: string;
  valueStream?: string;
  subScenarios?: string;
  // L2 新增（补全）
  coreCapabilities?: string;
  supportITSystems?: string;
  keyOrganizations?: string;
  keyDataEntities?: string;
  disconnectionPoints?: string;

  // --- L3 fields (11要素) ---
  businessProcess?: string;
  keyActivities?: string;
  aiOpportunity?: string;
  painPoints?: string;
  // L3 新增（补全）
  businessObjective?: string;
  capabilityUnits?: string;
  dataFlow?: string;
  positions?: string;
  supportSystems?: string;
  ontologyExtraction?: OntologyExtraction;

  // --- L4 fields (9要素) ---
  capabilityType?: string;
  masteryLevel?: string;
  currentRate?: string;
  talentGap?: string;
  // L4 新增（补全）
  l3KeyActivity?: string;
  capabilityUnitName?: string;
  capabilityDetail?: string;
  associatedPosition?: string;
}

// ============================================================
// 模拟数据
// ============================================================

const MOCK_PROJECTS = [
  { id: "1", name: "中石油 / 数字化转型项目" },
  { id: "2", name: "中信科 / 信创迁移项目" },
];

// ---- 前置分析（中石油数字化转型项目） ----
const preAnalysis: PreAnalysis = {
  industryValueChain:
    "上游：勘探开发（资源获取）→ 中游：管道运输（物流）→ 下游：炼化加工→成品销售→终端客户（用能）。" +
    "客户（中石油）所处环节：全产业链覆盖，核心优势在陆上勘探开发和管道网络。",
  customerPosition:
    "中国三大石油公司之一，行业前三。核心竞争力：陆上油气勘探开发技术领先，拥有全国最大油气管道网络。市场布局：国内为主、海外资产逐步扩大。",
  industryTrends:
    "① 政策：国家能源安全战略、信创国产化要求 → 加大国内勘探开发投入，IT系统需自主可控；" +
    "② 技术：AI大模型、工业互联网、数字孪生 → 推动智能化油田建设，降本增效；" +
    "③ 市场：油价波动、新能源替代压力 → 需控制成本，提高运营效率；" +
    "④ 竞争：国际石油公司数字化投入加大 → 倒逼客户加快数字化转型步伐。",
  strategicPositioning:
    "使命：'保障国家能源安全，建设国际一流能源公司'。" +
    "战略重点：增储上产、降本增效、绿色低碳、数字化转型。" +
    "对数字化的态度：将数字化转型作为核心战略之一，要求'业务与技术深度融合'。" +
    "近期调整：建设'智慧油田'、推动信创替代、成立数科公司。" +
    "关键KPI：勘探成功率、桶油成本、安全事故率、数字化覆盖率。",
  digitalizationDrivers:
    "① 降本增效：桶油成本需持续下降，IT投入产出可量化 → L1五维健康中'数字意识''数字神经'；" +
    "② 增储上产：勘探成功率、采收率提升需要技术支撑 → L1'能力链'中的勘探开发技术能力；" +
    "③ 安全合规：安全生产、环保合规、信创要求 → L1'IT系统'需标注国产化率和安全指标。",
};

// ---- L1 价值链节点（5个 + 五维健康） ----
const fiveDimL1: FiveDimHealth = {
  L5_数字意识: { score: 3, desc: "各价值链环节有量化目标，但生产环节目标与战略弱关联；创新投资占比仅20%" },
  L4_数字神经: { score: 2, desc: "勘探→开发数据延迟2周；变更失败率15%；跨域协同效率低" },
  L3_数字器官: { score: 2, desc: "GeoEast与Petrel不互通；SCADA用户NPS为-20；系统孤岛严重" },
  L2_数字血液: { score: 3, desc: "勘探数据人工录入错误率3%；开发无法实时获取；数据质量待提升" },
  L1_数字骨架: { score: 2, desc: "勘探算力排队3天；云成本年增30%；算力弹性不足" },
};

const l1Nodes: MapNode[] = [
  {
    id: "l1-1", level: "L1", name: "勘探与评估", parentId: null,
    mapType: "hypothesis", confidenceLevel: "高", sourceType: "搜索采集",
    coreActivities: "盆地评价、圈闭评价、油气藏评价、储量评估",
    capabilityChain: "地质研究 → 地球物理勘探 → 钻井评价 → 储量计算",
    itSystems: "GeoEast地震解释系统、ResForm地质建模、PEOffice生产管理",
    organization: "勘探开发研究院、各油田勘探事业部",
    fiveDimHealth: fiveDimL1,
  },
  {
    id: "l1-2", level: "L1", name: "开发建设", parentId: null,
    mapType: "hypothesis", confidenceLevel: "高", sourceType: "搜索采集",
    coreActivities: "开发方案编制、钻井工程、完井工程、地面建设",
    capabilityChain: "油藏工程 → 钻井工程 → 采油工程 → 地面工程",
    itSystems: "Petrel地质建模、Eclipse油藏数值模拟、Landmark钻井设计",
    organization: "开发事业部、钻探公司、工程建设公司",
    fiveDimHealth: {
      L5_数字意识: { score: 3, desc: "开发方案有标准流程，但数字化设计覆盖率仅60%" },
      L4_数字神经: { score: 3, desc: "钻井设计→施工流转周期2周，存在纸质交接" },
      L3_数字器官: { score: 2, desc: "Landmark与Petrel数据格式不兼容，需人工转换" },
      L2_数字血液: { score: 2, desc: "钻井实时数据回传延迟，井场→基地平均4小时" },
      L1_数字骨架: { score: 3, desc: "钻井仿真计算资源充足，但弹性调度能力不足" },
    },
  },
  {
    id: "l1-3", level: "L1", name: "生产运营", parentId: null,
    mapType: "hypothesis", confidenceLevel: "高", sourceType: "搜索采集",
    coreActivities: "采油采气、注水注气、修井作业、生产监测",
    capabilityChain: "油井管理 → 集输处理 → 动态监测 → 增产措施",
    itSystems: "油田生产物联网(A11)、SCADA系统、生产调度指挥系统",
    organization: "采油厂、井下作业公司、测试技术服务公司",
    fiveDimHealth: {
      L5_数字意识: { score: 2, desc: "一线员工对数字化目标认知不足，SOP覆盖仅50%" },
      L4_数字神经: { score: 2, desc: "异常井处置响应时间平均30分钟，远超行业标杆" },
      L3_数字器官: { score: 2, desc: "A11物联网平台覆盖率仅55%，老旧井站未接入" },
      L2_数字血液: { score: 3, desc: "SCADA数据采集频率达标(1s)，但数据质量合格率92%" },
      L1_数字骨架: { score: 2, desc: "边缘端算力不足，偏远井站依赖人工巡检" },
    },
  },
  {
    id: "l1-4", level: "L1", name: "集输储运", parentId: null,
    mapType: "hypothesis", confidenceLevel: "中", sourceType: "模型知识",
    coreActivities: "油气集输、处理加工、管道运输、储库管理",
    capabilityChain: "油气收集 → 脱水脱硫 → 管道输送 → 储罐管理",
    itSystems: "管道SCADA系统、泄漏监测系统、油库自动化系统",
    organization: "管道公司、储运公司、油气集输总厂",
    fiveDimHealth: {
      L5_数字意识: { score: 2, desc: "管道完整性管理意识强但数字化覆盖率仅55%" },
      L4_数字神经: { score: 3, desc: "泄漏检测到关阀响应平均8分钟，目标<5分钟" },
      L3_数字器官: { score: 2, desc: "泄漏监测系统误报率>30%，运维人员信任度低" },
      L2_数字血液: { score: 2, desc: "老旧管线（服役>30年）无传感器覆盖，数据缺失严重" },
      L1_数字骨架: { score: 2, desc: "管线沿线通信基础设施薄弱，偏远段无网络覆盖" },
    },
  },
  {
    id: "l1-5", level: "L1", name: "炼化销售", parentId: null,
    mapType: "hypothesis", confidenceLevel: "中", sourceType: "搜索采集",
    coreActivities: "原油加工、化工生产、产品销售、终端零售",
    capabilityChain: "炼油 → 乙烯 → 化工新材料 → 市场营销",
    itSystems: "MES生产执行系统、ERP(SAP)、加油站零售管理系统",
    organization: "炼化分公司、销售分公司、化工销售公司",
    fiveDimHealth: {
      L5_数字意识: { score: 3, desc: "炼化板块数字化投入占比高，但销售端数字化意识弱" },
      L4_数字神经: { score: 3, desc: "炼化→销售数据流转延迟1天，库存与销售计划脱节" },
      L3_数字器官: { score: 3, desc: "MES与ERP通过接口集成，但部分装置仍依赖手工录入" },
      L2_数字血液: { score: 2, desc: "加油站零售数据实时性好，但炼化装置化验数据仍为手工" },
      L1_数字骨架: { score: 4, desc: "炼化厂区IT基础设施较完善，数据中心PUE达标" },
    },
  },
];

// ---- L2 业务域（10个，补全8要素） ----
const l2Nodes: MapNode[] = [
  // === L1-1 下的 L2 ===
  {
    id: "l2-1", level: "L2", name: "地质研究域", parentId: "l1-1",
    mapType: "hypothesis", confidenceLevel: "高", sourceType: "搜索采集",
    domainType: "业务域",
    domainGoal: "提升探井成功率至68%（2025年基准62%）；勘探周期从启动到井位部署缩短10%",
    valueStream: "地质数据采集→综合研究→井位部署→钻探验证",
    subScenarios: "盆地模拟、区带评价、圈闭精细描述、非常规资源评价",
    coreCapabilities: "① 盆地/区带综合评价能力；② 非常规资源评估能力；③ 地质风险量化分析能力；④ 多学科数据融合解释能力",
    supportITSystems: "① ResForm（地质建模：构造建模、属性建模）；② PEOffice（生产管理：井史、分析）；③ 勘探数据管理平台（存储、版本管理、共享）",
    keyOrganizations: "组织：勘探开发研究院、各油田勘探事业部；岗位：勘探地质师（地质研究、解释评价）、地球物理师（物探数据解释）",
    keyDataEntities: "地震数据（原始炮集、叠加数据）、测井数据（曲线、地层参数）、地质模型（网格、属性）、井位坐标、勘探风险数据、成果报告",
    disconnectionPoints: "① 多学科数据分散在GeoEast/Petrel/ResForm等系统中，跨软件整合需2-3天；② 地质研究成果与钻井设计脱节，井位部署方案反复修改",
    fiveDimHealth: {
      L5_数字意识: { score: 3, desc: "域目标已量化，但未分解至具体岗位KPI" },
      L4_数字神经: { score: 2, desc: "研究→部署流转周期3个月，缺乏并行协作机制" },
      L3_数字器官: { score: 2, desc: "ResForm建模模块使用率仅40%，系统功能未充分利用" },
      L2_数字血液: { score: 3, desc: "合格率98%，但漏报率5%；数据质量有隐患" },
      L1_数字骨架: { score: 3, desc: "研究院算力资源充足，但野外人员无法远程访问" },
    },
  },
  {
    id: "l2-2", level: "L2", name: "地球物理域", parentId: "l1-1",
    mapType: "hypothesis", confidenceLevel: "高", sourceType: "搜索采集",
    domainType: "业务域",
    domainGoal: "地震资料处理周期缩短30%；解释精度提升至90%+；采集数据合格率≥98%",
    valueStream: "野外采集→室内处理→构造解释→储层预测",
    subScenarios: "高精度三维地震、VSP垂直地震、微地震监测",
    coreCapabilities: "① 海上/陆地复杂地表地震采集技术；② 三维地震大数据处理算法能力；③ 叠前深度偏移成像能力；④ 储层预测与流体检测能力",
    supportITSystems: "① GeoEast（地震数据处理：去噪、偏移、成像）；② Petrel（地震解释：层位追踪、断层识别）；③ 采集质控系统（实时监控、参数调整）",
    keyOrganizations: "组织：物探事业部、海洋地质研究院；岗位：物探工程师（采集设计、数据处理）、解释工程师（层位标定、构造解释）",
    keyDataEntities: "地震原始数据（炮集记录）、速度模型、叠加/偏移数据体、层位解释数据、断层数据、储层属性体",
    disconnectionPoints: "① GeoEast与Petrel系统不互通，模型数据需手动导入导出，易出错；② 野外采集数据回传延迟3-5天，影响后续处理流程效率",
    fiveDimHealth: {
      L5_数字意识: { score: 3, desc: "域目标量化清晰，但野外人员对数据质量目标认知不足" },
      L4_数字神经: { score: 2, desc: "数据采集至处理环节延迟3天，流程流转效率低" },
      L3_数字器官: { score: 2, desc: "GeoEast深度偏移模块只有2名熟练用户，功能采纳率低" },
      L2_数字血液: { score: 2, desc: "野外采集数据回传延迟3-5天；数据格式版本不统一" },
      L1_数字骨架: { score: 2, desc: "物探数据处理需要GPU集群，排队等待平均3天" },
    },
  },
  // === L1-3 下的 L2 ===
  {
    id: "l2-3", level: "L2", name: "采油工程域", parentId: "l1-3",
    mapType: "hypothesis", confidenceLevel: "高", sourceType: "用户上传",
    domainType: "业务域",
    domainGoal: "自然递减率控制在8%以内；机采系统效率提升至35%；修井作业成本降低10%",
    valueStream: "举升工艺选型→参数优化→工况诊断→措施调整",
    subScenarios: "人工举升优化、堵水调剖、酸压增产、智能分层注水",
    coreCapabilities: "① 机采系统效率优化能力；② 油井工况实时诊断能力；③ 注水开发动态调配能力；④ 增产措施筛选与效果评价能力",
    supportITSystems: "① 油田生产物联网A11（工况数据采集、实时传输）；② 机采优化系统（示功图分析、参数推荐）；③ 修井调度系统（派工、跟踪）",
    keyOrganizations: "组织：采油厂工程技术大队、井下作业公司；岗位：采油工程师（举升设计、参数优化）、修井监督（作业质量、安全管控）",
    keyDataEntities: "示功图数据、动液面数据、注水量/注水压力、产液量/含水率、修井作业记录、增产措施效果评价",
    disconnectionPoints: "① 功图诊断结果与修井调度系统未打通，告警→派工链路未闭环；② 注水井调节依赖人工经验，动态调水周期长达1周",
    fiveDimHealth: {
      L5_数字意识: { score: 3, desc: "采油厂管理人员对数字化接受度高，一线人员培训不足" },
      L4_数字神经: { score: 2, desc: "工况诊断→修井派工链路未闭环，人工中转耗时半天" },
      L3_数字器官: { score: 2, desc: "机采优化系统井下泵工况识别准确率仅78%" },
      L2_数字血液: { score: 3, desc: "示功图采集频率达标(1次/小时)，但深井数据丢包率15%" },
      L1_数字骨架: { score: 2, desc: "偏远井站无4G/5G覆盖，数据需人工到场采集" },
    },
  },
  {
    id: "l2-4", level: "L2", name: "生产监测域", parentId: "l1-3",
    mapType: "hypothesis", confidenceLevel: "中", sourceType: "搜索采集",
    domainType: "业务域",
    domainGoal: "实现80%以上井站数字化覆盖；实时数据采集延迟<1s；异常预警准确率>85%",
    valueStream: "传感器部署→数据采集→边缘计算→云端分析",
    subScenarios: "油井工况诊断、管线泄漏预警、能耗优化、设备预测性维护",
    coreCapabilities: "① 多参数融合异常检测能力；② 边缘计算部署与运维能力；③ 设备健康状态评估与RUL预测能力；④ 能耗建模与优化调度能力",
    supportITSystems: "① SCADA系统（实时数据采集、报警管理）；② 生产调度指挥系统（大屏监控、调度指令）；③ 能耗管理平台（能耗统计、优化建议）",
    keyOrganizations: "组织：生产运行部、自动化中心；岗位：自动化工程师（传感器部署、SCADA维护）、数据分析师（异常检测模型调优）",
    keyDataEntities: "传感器时序数据（压力/温度/流量/振动）、报警记录、设备台账、能耗数据、巡检记录",
    disconnectionPoints: "① 老旧管线（服役>30年）传感器覆盖不足，数据质量差；② SCADA告警阈值静态设置，工况变化后频繁误报，导致'狼来了'效应",
    fiveDimHealth: {
      L5_数字意识: { score: 2, desc: "管理层重视安全生产监控，但缺乏系统性数字化规划" },
      L4_数字神经: { score: 2, desc: "SCADA告警到现场确认平均30分钟，自动化程度低" },
      L3_数字器官: { score: 2, desc: "泄漏监测系统误报率>30%，运维人员信任度低" },
      L2_数字血液: { score: 2, desc: "小泄漏（泄漏量<1%）检测延迟>30分钟；传感器数据缺失率达20%" },
      L1_数字骨架: { score: 2, desc: "偏远管线段无通信覆盖，边缘计算设备部署为零" },
    },
  },
  // === L1-4 下的 L2（现状地图已验证） ===
  {
    id: "l2-5", level: "L2", name: "管道完整性管理域", parentId: "l1-4",
    mapType: "current", verificationStatus: "成立", confidenceLevel: "高", sourceType: "用户上传",
    domainType: "业务域",
    domainGoal: "管道失效率降低至0.12次/千公里·年；内检测覆盖率提升至80%；缺陷修复周期缩短50%",
    valueStream: "风险识别→检测评价→维修维护→效能评估",
    subScenarios: "内检测(ILI)、外检测、阴极保护、缺陷评估与修复",
    coreCapabilities: "① 管道内检测(ILI)数据分析能力；② 缺陷评估与剩余强度/寿命预测能力；③ 阴极保护有效性评价能力；④ 基于风险的检验(RBI)规划能力",
    supportITSystems: "① 管道完整性管理系统PIMS（风险评价、检测计划、缺陷跟踪）；② GIS管道地图（空间展示、周边环境分析）；③ ILI数据分析软件（缺陷识别、聚类分析）",
    keyOrganizations: "组织：管道完整性管理中心、各管道分公司；岗位：完整性工程师（风险评价、检测计划）、腐蚀工程师（CP监测、防腐方案）",
    keyDataEntities: "内检测数据（金属损失、变形）、外检测数据（涂层破损、CP电位）、管道属性（材质、壁厚、投运日期）、缺陷维修记录、风险评价报告",
    disconnectionPoints: "① 内检测数据量大（单次检测TB级），数据分析依赖外方，周期长（3-6个月）；② 缺陷维修后未及时回填PIMS，效能评估数据不完整",
    fiveDimHealth: {
      L5_数字意识: { score: 4, desc: "管道完整性管理法规要求严格，管理层数字化意识强" },
      L4_数字神经: { score: 3, desc: "检测→评价→维修流程清晰，但周期偏长（平均90天）" },
      L3_数字器官: { score: 2, desc: "PIMS功能完善但UI老旧，一线工程师使用意愿低" },
      L2_数字血液: { score: 2, desc: "老旧管线（服役>30年）无历史内检测数据，风险评估依赖保守假设" },
      L1_数字骨架: { score: 3, desc: "管道沿线通信逐步完善，但山区段仍为盲区" },
    },
  },
  // === L1-5 下的 L2 ===
  {
    id: "l2-6", level: "L2", name: "智能炼化域", parentId: "l1-5",
    mapType: "hypothesis", confidenceLevel: "低", sourceType: "模型知识",
    domainType: "业务域",
    domainGoal: "炼油综合能耗降低5%；乙烯收率提升2个百分点；APC投用率≥90%",
    valueStream: "原油采购→常减压→催化裂化→加氢精制→乙烯裂解",
    subScenarios: "APC先进控制、实时优化(RTO)、计划排产优化、能源管理系统",
    coreCapabilities: "① 多变量预测控制(APC)建模与运维能力；② 实时在线优化(RTO)实施能力；③ 全厂计划排产与调度优化能力；④ 能源平衡与能效评价能力",
    supportITSystems: "① MES生产执行系统（物料平衡、生产统计）；② APC系统（DMC控制器、在线优化）；③ 计划排产系统（PIMS/ORION）；④ 能源管理系统EMS",
    keyOrganizations: "组织：炼化分公司技术处、各装置车间；岗位：过程控制工程师（APC建模、调优）、生产计划员（排产、调度）",
    keyDataEntities: "装置实时运行数据（温度/压力/流量/液位）、化验分析数据、原料/产品库存、能耗数据（电/汽/燃料）、生产计划、APC模型参数",
    disconnectionPoints: "① APC投用率仅63%，模型频繁失效需人工复位，瓶颈是原料性质波动大；② 计划排产与装置实际能力有偏差，月度计划执行率仅85%",
    fiveDimHealth: {
      L5_数字意识: { score: 4, desc: "炼化板块数字化起步早，APC/RTO认知度高" },
      L4_数字神经: { score: 3, desc: "排产→执行→反馈链路存在人工断点，月计划调整频繁" },
      L3_数字器官: { score: 2, desc: "APC投用率仅63%，模型鲁棒性不足，需频繁人工干预" },
      L2_数字血液: { score: 3, desc: "化验数据仍为手工录入，延迟2-4小时，影响APC实时性" },
      L1_数字骨架: { score: 4, desc: "炼化厂区网络/DCS基础设施完善，具备智能化升级条件" },
    },
  },
  // === 横向支撑域 ===
  {
    id: "l2-s1", level: "L2", name: "人力资源域", parentId: null,
    mapType: "hypothesis", confidenceLevel: "中", sourceType: "行业模板",
    domainType: "职能域",
    domainGoal: "关键岗位人才密度提升至0.8；数字化人才占比达25%；培训覆盖率100%",
    valueStream: "人才规划→招聘选拔→培养发展→绩效激励",
    subScenarios: "专家图谱、技能矩阵、岗位胜任力模型、人才盘点",
    coreCapabilities: "① 基于业务战略的人才需求预测能力；② 数字化人才画像与精准招聘能力；③ 能力差距量化评估能力；④ 关键人才保留与继任计划能力",
    supportITSystems: "① HR系统SAP SuccessFactors（员工主数据、绩效）；② 培训管理平台（课程管理、学习记录）；③ 人才盘点系统（九宫格、继任计划）",
    keyOrganizations: "组织：人力资源部、各业务部门HRBP；岗位：HRBP（业务对接、人才规划）、培训专员（课程开发、培训运营）",
    keyDataEntities: "员工主数据、岗位任职资格、技能标签、培训记录、绩效评估、人才盘点九宫格、继任计划",
    disconnectionPoints: "① 人才信息分散在HR系统/科研成果库/项目档案中，无统一视图；② 培训内容与业务场景脱节，培训后能力转化率不足30%",
    fiveDimHealth: {
      L5_数字意识: { score: 2, desc: "HR数字化停留在人事管理层面，人才分析能力薄弱" },
      L4_数字神经: { score: 2, desc: "招聘流程平均45天，人才需求到入职周期过长" },
      L3_数字器官: { score: 3, desc: "SAP系统覆盖主数据管理，但人才分析模块未启用" },
      L2_数字血液: { score: 2, desc: "员工技能数据严重缺失，70%员工无完整技能标签" },
      L1_数字骨架: { score: 3, desc: "HR系统云化已完成，但与其他系统集成不够" },
    },
  },
  {
    id: "l2-s2", level: "L2", name: "物资管理域", parentId: null,
    mapType: "hypothesis", confidenceLevel: "高", sourceType: "搜索采集",
    domainType: "职能域",
    domainGoal: "库存周转率提升20%；采购周期缩短35%；物资供应保障率100%",
    valueStream: "需求计划→招标采购→仓储配送→消耗核销",
    subScenarios: "智能预测补货、供应商风险管理、物资全生命周期追踪",
    coreCapabilities: "① 基于生产计划的需求预测能力；② 采购成本控制与谈判能力；③ 仓储自动化管理能力（WMS/AGV）；④ 库存优化能力（安全库存、JIT）；⑤ 供应商全生命周期管理能力",
    supportITSystems: "① ERP（采购订单管理、库存台账、财务结算）；② SRM（供应商准入、绩效评估、询报价）；③ WMS（入库、出库、盘点、货位管理）；④ 采购招标平台（公开招标、电子评标）",
    keyOrganizations: "组织：采购中心、仓储部、供应链部；岗位：物资计划员（需求计划、库存分析）、采购专员（招标、合同）、仓库管理员（入库、出库、盘点）",
    keyDataEntities: "物资主数据（编码/名称/规格/价格）、库存台账（库存量/库龄/批次）、采购订单、入库单、出库单、供应商信息（资质/绩效）",
    disconnectionPoints: "① 物资计划独立于生产计划制定，紧急采购频发（占30%）、物资积压；② 仓储数据人工录入ERP，数据延迟1天，库存准确性不足；③ 供应商协同低效：依赖邮件/传真，订单状态不可视",
    fiveDimHealth: {
      L5_数字意识: { score: 3, desc: "管理层重视供应链数字化，但落地推进缓慢" },
      L4_数字神经: { score: 2, desc: "采购审批多级手工，平均3天，紧急需求无法快速通过" },
      L3_数字器官: { score: 2, desc: "WMS覆盖不全，部分仓库仍用Excel管理库存" },
      L2_数字血液: { score: 2, desc: "库存数据延迟1天；物资编码不统一导致重复采购" },
      L1_数字骨架: { score: 3, desc: "ERP上云已完成，仓储端网络覆盖有待加强" },
    },
  },
  {
    id: "l2-s3", level: "L2", name: "数据与AI平台域", parentId: null,
    mapType: "hypothesis", confidenceLevel: "中", sourceType: "用户上传",
    domainType: "共性技术域",
    domainGoal: "建成统一数据湖；AI模型复用率达60%；模型开发周期缩短50%；推理延迟<100ms(P99)",
    valueStream: "数据采集→数据治理→特征工程→模型训练→推理服务",
    subScenarios: "湖仓一体架构、数据资产目录、MLOps流水线、知识图谱",
    coreCapabilities: "① 千卡级分布式训练调度能力；② 模型推理加速能力（量化/剪枝）；③ MLOps工程化能力（CI/CD/CT）；④ 数据标注与质量管理能力",
    supportITSystems: "① 数据湖平台（Hudi/Iceberg + Spark/Flink）；② 机器学习平台Kubeflow（实验管理、模型注册）；③ 推理服务平台Triton（模型deployment、API网关）；④ 特征存储Feast（特征复用、版本管理）",
    keyOrganizations: "组织：数字化中心、AI算法部；岗位：算法工程师（模型开发、调优）、MLOps工程师（部署、监控）、数据治理工程师（数据质量、目录）",
    keyDataEntities: "训练数据集（原始/清洗后）、测试数据集、标注数据、特征库、模型文件（pkl/onnx）、模型版本记录、推理日志、监控指标（延迟/吞吐/准确率）",
    disconnectionPoints: "① 算法团队对业务痛点了解不足，开发模型无法解决实际问题；② 训练数据与线上实际数据分布不一致，模型上线后效果快速衰减；③ 开发环境与生产环境不统一，模型部署周期平均2周",
    fiveDimHealth: {
      L5_数字意识: { score: 3, desc: "AI平台建设列入公司重点工程，但业务部门认知参差不齐" },
      L4_数字神经: { score: 2, desc: "数据申请到获取平均7天，数据流转效率低" },
      L3_数字器官: { score: 2, desc: "Kubeflow平台刚上线，用户数<10，功能待验证" },
      L2_数字血液: { score: 2, desc: "数据质量报告缺失，训练数据无系统化版本管理" },
      L1_数字骨架: { score: 2, desc: "GPU资源池规模不足（当前32卡），排队等待>4小时" },
    },
  },
  {
    id: "l2-s4", level: "L2", name: "网络安全域", parentId: null,
    mapType: "hypothesis", confidenceLevel: "中", sourceType: "搜索采集",
    domainType: "共性技术域",
    domainGoal: "工控安全事件响应时间<30分钟；等保三级覆盖率100%；安全事件同比下降50%",
    valueStream: "风险评估→防护部署→监测预警→应急响应",
    subScenarios: "工控安全、数据安全治理、零信任架构、安全运营中心(SOC)",
    coreCapabilities: "① 工控系统安全风险评估能力；② 安全态势感知与威胁狩猎能力；③ 数据安全分级分类与治理能力；④ 应急响应与取证溯源能力",
    supportITSystems: "① SOC平台（SIEM日志分析、告警聚合）；② 工控安全监测系统（流量审计、异常检测）；③ 数据安全平台（分类分级、DLP）；④ 漏洞管理平台（扫描、跟踪修复）",
    keyOrganizations: "组织：信息安全部、数字化中心安全组；岗位：安全运维工程师（SOC值守、事件处置）、安全架构师（方案设计、评审）",
    keyDataEntities: "安全日志（防火墙/IDS/WAF）、告警事件、漏洞清单、资产台账、安全策略配置、事件处置工单",
    disconnectionPoints: "① 工控系统与IT系统安全策略分离，OT安全监测覆盖不足；② 安全告警日均500+条，误报率高，SOC人员疲于应对；③ 数据安全分类分级刚起步，敏感数据分布不清",
    fiveDimHealth: {
      L5_数字意识: { score: 3, desc: "等保合规驱动，安全意识逐年提升，但主动防御思维不足" },
      L4_数字神经: { score: 3, desc: "安全事件响应流程清晰，但平均响应时间40分钟（目标<30分钟）" },
      L3_数字器官: { score: 2, desc: "SOC平台告警误报率>50%，安全分析师倦怠严重" },
      L2_数字血液: { score: 2, desc: "OT侧安全日志采集缺失，工控系统看不见、防不住" },
      L1_数字骨架: { score: 3, desc: "安全基础设施投入逐年增加，但工控侧投入偏低" },
    },
  },
];

// ---- L3 细分场景（5个，补全11要素含本体抽取） ----
const l3Nodes: MapNode[] = [
  {
    id: "l3-1", level: "L3", name: "探井井位智能优选", parentId: "l2-1",
    mapType: "hypothesis", confidenceLevel: "中", sourceType: "模型知识",
    businessObjective: "① 井位论证周期从3个月缩短至1个月；② 探井成功率从62%提升至68%；③ 多学科数据整合效率提升50%",
    businessProcess: "多源数据整合→地质风险量化→经济评价→井位排队优选",
    keyActivities: "地震属性提取、烃源岩评价、圈闭风险分析、蒙特卡洛模拟、经济指标测算",
    capabilityUnits: "多源地质数据融合能力、地质风险量化建模能力、蒙特卡洛不确定性分析能力、投资组合优化能力",
    dataFlow: "地震数据（GeoEast）→ 地质模型（ResForm）→ 风险参数 → 经济模型 → 井位排序结果 → 决策报告",
    positions: "勘探地质师（数据整合、风险评价）、地球物理师（地震属性提取）、经济评价师（NPV/IRR测算）",
    supportSystems: "① GeoEast（地震数据提取：属性计算、层位导出）；② ResForm（地质建模：构造模型输出）；③ 井位优选系统（排队算法、可视化对比）",
    painPoints: "① 现有井位论证依赖专家经验，周期长（平均3个月）；② 多学科数据分散在不同系统中，整合耗时；③ 探井成功率近年徘徊在62%，低于国际先进水平(70%)",
    ontologyExtraction: {
      entities: "地震测线、地质圈闭、烃源岩、储层、风险概率、NPV(净现值)、井位坐标",
      relations: "圈闭→包含→储层；地震数据→解释→地质模型；井位→关联→风险评价",
      rules: "若地质风险概率>0.6，则降低井位优先级；若NPV<0，则排除该井位；若储量规模>100万吨，则提升优先级",
      actions: "数据整合、风险量化、经济评价、井位排序、决策审批",
    },
    aiOpportunity: "利用图神经网络融合地震/地质/测井多模态数据，辅助井位排序决策（基于本体中的圈闭/储层/风险概率实体和规则）",
    fiveDimHealth: {
      L5_数字意识: { score: 2, desc: "井位论证专家清楚数据质量重要性，但缺乏量化意识" },
      L4_数字神经: { score: 2, desc: "数据整合占论证周期40%，大量时间花在'找数据'而非'分析'" },
      L3_数字器官: { score: 2, desc: "井位优选系统UI复杂，只有2人能熟练操作" },
      L2_数字血液: { score: 2, desc: "跨学科数据版本不一致，经常出现'用错数据'的情况" },
      L1_数字骨架: { score: 3, desc: "研究院计算资源充足，但软件许可限制并行用户数" },
    },
  },
  {
    id: "l3-2", level: "L3", name: "地震资料智能解释", parentId: "l2-2",
    mapType: "hypothesis", confidenceLevel: "中", sourceType: "搜索采集",
    businessObjective: "① 人工解释工作量减少60%；② 断层识别准确率≥92%；③ 三维数据体解释周期缩短50%",
    businessProcess: "数据加载→层位标定→断层解释→属性分析→储层预测",
    keyActivities: "合成记录标定、层位追踪、断层自动识别、AVO属性分析、储层参数反演",
    capabilityUnits: "合成地震记录标定能力、深度学习断层识别模型训练能力、层位自动追踪算法调优能力、AVO属性异常检测能力",
    dataFlow: "地震数据体（GeoEast）→ 合成记录标定 → 深度学习推理 → 断层/层位结果 → Petrel可视化 → 储层预测报告",
    positions: "解释工程师（层位标定、质控）、算法工程师（模型训练、调优）、物探工程师（属性分析、储层预测）",
    supportSystems: "① GeoEast（地震数据加载、数据预处理）；② 断层识别AI模块（CNN推理、后处理）；③ Petrel（解释结果可视化、质控编辑）",
    painPoints: "① 三维地震数据体量巨大（单区块TB级），人工解释效率低；② 复杂构造区断层组合多解性强；③ 年轻解释人员培养周期长（3-5年）",
    ontologyExtraction: {
      entities: "地震数据体、地震层位、断层、合成记录、速度模型、储层属性体",
      relations: "层位→穿过→地震数据体；断层→切割→层位；合成记录→标定→层位",
      rules: "若相邻道相似度<0.7，则标记为潜在断层；若层位连续性中断，则触发人工复核",
      actions: "数据加载、层位标定、断层识别、属性计算、储层预测",
    },
    aiOpportunity: "基于深度学习的断层自动识别与层位智能追踪（引用本体中的断层/层位实体和相似度规则），替代60%+人工解释工作",
    fiveDimHealth: {
      L5_数字意识: { score: 2, desc: "年轻解释人员对AI辅助持开放态度，资深人员偏好传统方法" },
      L4_数字神经: { score: 2, desc: "解释周期严重受限于人工速度，1个区块3人月" },
      L3_数字器官: { score: 2, desc: "AI模块与GeoEast集成不深，需独立启动，体验割裂" },
      L2_数字血液: { score: 2, desc: "训练数据标签依赖专家，每人天仅标注2km²，数据积累慢" },
      L1_数字骨架: { score: 2, desc: "GPU推理资源不足，大区块AI预测需排队>8小时" },
    },
  },
  {
    id: "l3-3", level: "L3", name: "机采井智能工况诊断", parentId: "l2-3",
    mapType: "current", verificationStatus: "部分成立", confidenceLevel: "高", sourceType: "用户上传",
    businessObjective: "① 异常工况识别准确率≥95%；② 诊断到派工闭环时间<30分钟；③ 试点井数扩展至500口",
    businessProcess: "功图采集→特征提取→工况分类→措施推荐→效果跟踪",
    keyActivities: "示功图实时回传、CNN模型推理、异常井自动告警、优化方案推送、修井效果评价",
    capabilityUnits: "示功图CNN-LSTM模型训练能力、工况特征工程能力、异常阈值动态调整能力、修井措施知识库维护能力",
    dataFlow: "示功图传感器（A11物联网）→ 边缘采集终端 → CNN推理引擎 → 异常告警（SCADA）→ 修井调度系统 → 效果反馈数据库",
    positions: "采油工程师（模型调优、措施推荐）、自动化工程师（传感器维护、数据传输）、修井监督（派工执行、效果评价）",
    supportSystems: "① 油田生产物联网A11（功图采集、数据回传）；② 工况诊断AI引擎（CNN-LSTM推理、异常分类）；③ 修井调度系统（派工、跟踪、效果回填）",
    painPoints: "① 已上线试点200口井，准确率91%但仍有漏报（深井泵工况识别困难）；② 与修井调度系统未打通，告警→派工链路未闭环",
    ontologyExtraction: {
      entities: "示功图、工况类型（正常/供液不足/气锁/泵漏等12类）、修井措施、修井效果评价",
      relations: "示功图→分类为→工况类型；异常工况→触发→修井派工；修井措施→改善→工况",
      rules: "若示功图形状变化率>30%且持续>4小时，则判定为异常；若深井（泵深>3000m）置信度<0.8，则推送人工复核",
      actions: "功图采集、工况分类、异常告警、措施推荐、效果评价",
    },
    aiOpportunity: "基于CNN-LSTM的示功图实时诊断模型（引用本体中示功图/工况类型实体和形状变化率规则），准确率已达91%，覆盖12种工况类型，需扩展深井泵工况",
    fiveDimHealth: {
      L5_数字意识: { score: 3, desc: "采油厂管理层已看到AI效果，主动要求扩展试点范围" },
      L4_数字神经: { score: 2, desc: "诊断准确率91%但人工复核仍占30%工作量，闭环未形成" },
      L3_数字器官: { score: 3, desc: "AI引擎运行稳定，但需独立登录查看，未嵌入日常作业流" },
      L2_数字血液: { score: 3, desc: "示功图数据质量较好，但修井效果数据回填不及时" },
      L1_数字骨架: { score: 2, desc: "边缘端推理延迟<200ms达标，但深井井站4G信号不稳定" },
    },
  },
  {
    id: "l3-4", level: "L3", name: "集输管线泄漏智能预警", parentId: "l2-4",
    mapType: "hypothesis", confidenceLevel: "低", sourceType: "模型知识",
    businessObjective: "① 泄漏误报率从>30%降低至<5%；② 小泄漏（<1%流量）检测延迟<10分钟；③ 定位精度≤50米",
    businessProcess: "压力/流量/声波多参数采集→异常检测→定位推算→联动关阀",
    keyActivities: "负压波信号处理、流量平衡计算、声波特征提取、GPS定位、关阀联动控制",
    capabilityUnits: "负压波到达时间差定位能力、多参数融合异常检测算法能力、声波信号降噪处理能力、管道水力模型仿真能力",
    dataFlow: "压力/流量/声波传感器 → RTU边缘采集 → 多参数融合检测引擎 → 定位推算 → SCADA报警 → 关阀指令",
    positions: "自动化工程师（传感器部署、边缘计算维护）、算法工程师（异常检测模型调优）、管道调度员（报警响应、关阀确认）",
    supportSystems: "① 管道SCADA系统（实时数据采集、报警管理）；② 泄漏检测AI引擎（Kalman滤波+Isolation Forest）；③ 管道水力仿真系统（在线定位推算）",
    painPoints: "① 老旧管线传感器覆盖不足，数据质量差；② 现有系统误报率高(>30%)，运维人员不信任；③ 小泄漏(泄漏量<1%)检测延迟>30分钟",
    ontologyExtraction: {
      entities: "压力信号、流量信号、声波信号、负压波、泄漏定位、阀门状态、管道段",
      relations: "压力信号→检测→负压波；泄漏定位→关联→管道段；阀门→控制→管道段",
      rules: "若负压波到达时间差>2s，则推算泄漏点距离；若多参数异常得分>0.8，则触发泄漏预警；若泄漏量<1%，则标记为小泄漏（低优先级）",
      actions: "参数采集、异常检测、定位推算、报警发布、关阀联动",
    },
    aiOpportunity: "多参数融合异常检测模型（Kalman滤波+Isolation Forest，引用本体中压力/流量/声波实体和异常得分规则），误报率目标<5%",
    fiveDimHealth: {
      L5_数字意识: { score: 2, desc: "安全部门高度重视，但预算投入集中在事后处置而非预防" },
      L4_数字神经: { score: 2, desc: "报警到确认平均8分钟，小泄漏经常被忽略" },
      L3_数字器官: { score: 1, desc: "现有泄漏检测系统误报率>30%，管道调度员基本忽略系统告警" },
      L2_数字血液: { score: 1, desc: "老旧管线无传感器，小泄漏无法检测；传感器缺失率达40%" },
      L1_数字骨架: { score: 1, desc: "偏远管线段无通信覆盖，边缘计算设备部署为零" },
    },
  },
  {
    id: "l3-5", level: "L3", name: "人才专家知识图谱", parentId: "l2-s1",
    mapType: "hypothesis", confidenceLevel: "中", sourceType: "行业模板",
    businessObjective: "① 专家检索响应时间从'熟人打听3天'缩短至'系统搜索5分钟'；② 人才画像完整度≥80%；③ 跨部门人才匹配成功率提升50%",
    businessProcess: "实体抽取→关系构建→图谱存储→智能检索→人才推荐",
    keyActivities: "简历信息抽取、项目经历NER、技能标签体系构建、图谱可视化、知识问答",
    capabilityUnits: "NLP信息抽取能力（NER/关系抽取）、知识图谱Schema设计能力、图谱查询SPARQL/Cypher编写能力、人才匹配推荐算法能力",
    dataFlow: "HR系统（员工主数据）→ 项目管理系统（项目经历）→ 科研成果库（论文/专利）→ 知识图谱平台 → 人才检索门户",
    positions: "知识图谱工程师（Schema设计、实体抽取）、HRBP（人才需求输入、结果验证）、数据工程师（数据清洗、ETL）",
    supportSystems: "① HR系统SAP SuccessFactors（员工基本信息）；② 科研成果库（论文、专利、项目）；③ 知识图谱平台Neo4j（存储、查询、推理）",
    painPoints: "① 人才信息分散在HR系统、科研成果库、项目档案中，无统一视图；② 专家检索依赖'熟人推荐'，跨部门协作效率低；③ 退休专家经验无法传承",
    ontologyExtraction: {
      entities: "员工、技能、项目、论文、专利、部门、岗位、专家标签",
      relations: "员工→拥有→技能；员工→参与→项目；员工→发表→论文；专家标签→关联→技能",
      rules: "若员工技能覆盖度>80%且项目经验>5年，则标记为'资深专家'；若技能匹配度>60%，则推荐为候选人",
      actions: "实体抽取、关系构建、图谱存储、智能检索、人才推荐",
    },
    aiOpportunity: "构建企业级专家知识图谱（引用本体中员工/技能/项目实体和技能覆盖度规则），实现'谁能解决这个技术难题'的智能语义匹配",
    fiveDimHealth: {
      L5_数字意识: { score: 2, desc: "HR部门认可知识图谱价值，但缺乏技术实施能力" },
      L4_数字神经: { score: 1, desc: "目前完全依赖'熟人打听'模式，跨部门检索效率极低" },
      L3_数字器官: { score: 1, desc: "无知识图谱平台，技能标签体系尚未建立" },
      L2_数字血液: { score: 1, desc: "员工技能数据严重缺失，70%员工无结构化技能标签" },
      L1_数字骨架: { score: 2, desc: "基础设施可支撑，但需采购图数据库等基础软件" },
    },
  },
];

// ---- L4 人才地图（4个岗位，补全9要素） ----
const l4Nodes: MapNode[] = [
  {
    id: "l4-1", level: "L4", name: "地球物理AI算法工程师", parentId: "l3-2",
    mapType: "hypothesis", confidenceLevel: "中", sourceType: "行业模板",
    l3KeyActivity: "断层自动识别（CNN推理）",
    capabilityUnitName: "深度学习断层识别模型训练能力",
    capabilityType: "硬技能+工具操作(AI+物探复合型)",
    capabilityDetail: "能够利用CNN/UNet架构训练地震断层自动识别模型；掌握PyTorch/TensorFlow深度学习框架；理解地震数据特征（道集/叠加/偏移）并能设计合理的训练集/验证集划分策略",
    masteryLevel: "高级/专家（稀缺）",
    associatedPosition: "AI算法工程师（物探方向）",
    currentRate: "35%",
    talentGap: "需3-5名深度学习+地震解释背景的复合人才，目前仅有1名外协。建议：① 外部招聘1-2名AI+物探背景博士；② 内部选拔3名物探工程师参加6个月AI实训",
  },
  {
    id: "l4-2", level: "L4", name: "采油工程数据分析师", parentId: "l3-3",
    mapType: "current", verificationStatus: "成立", confidenceLevel: "高", sourceType: "用户上传",
    l3KeyActivity: "CNN模型推理（工况分类）",
    capabilityUnitName: "示功图CNN-LSTM模型训练与调优能力",
    capabilityType: "硬技能+业务知识（数据分析应用型）",
    capabilityDetail: "能够基于CNN-LSTM架构训练示功图工况分类模型；掌握时间序列特征工程方法（FFT/小波变换）；理解12种采油工况的物理机理并能将领域知识融入模型设计",
    masteryLevel: "中级（可独立完成模型调优）",
    associatedPosition: "数据分析师（采油工程方向）",
    currentRate: "70%",
    talentGap: "现有2名数据分析师，可独立完成功图模型调优，但缺乏大数据工程能力（Spark/Flink）。建议：① 安排参加大数据工程培训（2周）；② 每人负责1个子场景的模型优化并输出知识文档",
  },
  {
    id: "l4-3", level: "L4", name: "工业物联网工程师", parentId: "l3-4",
    mapType: "hypothesis", confidenceLevel: "高", sourceType: "搜索采集",
    l3KeyActivity: "负压波信号处理（边缘计算）",
    capabilityUnitName: "边缘计算设备部署与无线传感网组网能力",
    capabilityType: "硬技能+工具操作（IoT基础设施型）",
    capabilityDetail: "能够设计油气管线多参数（压力/流量/声波/振动）传感器部署方案；掌握LoRa/4G/5G无线传感网组网与协议配置；具备Edge AI（边缘端推理）设备选型与部署能力",
    masteryLevel: "中级（缺乏专职人员，缺口严重）",
    associatedPosition: "工业物联网工程师",
    currentRate: "20%",
    talentGap: "无专职人员，目前由自动化仪表工程师兼任，不具备边缘计算和无线传感网部署能力。建议：① 外部招聘1名IoT工程师（有油气行业经验优先）；② 送2名自动化工程师参加边缘计算认证培训（华为HCIA-IoT）",
  },
  {
    id: "l4-4", level: "L4", name: "知识图谱架构师", parentId: "l3-5",
    mapType: "hypothesis", confidenceLevel: "低", sourceType: "模型知识",
    l3KeyActivity: "实体抽取（NER+关系抽取）",
    capabilityUnitName: "企业知识图谱Schema设计与图数据库管理能力",
    capabilityType: "硬技能+软技能（AI平台架构型）",
    capabilityDetail: "能够设计企业级人才知识图谱Schema（员工/技能/项目/论文等实体及其关系）；熟练使用Neo4j/JanusGraph等图数据库；掌握SPARQL/Cypher查询语言；能与业务部门沟通提炼图谱建模需求",
    masteryLevel: "高级/专家（缺口）",
    associatedPosition: "知识图谱架构师 / 数据架构师",
    currentRate: "0%",
    talentGap: "尚无此岗位，知识图谱构建能力为零。建议：① 外部引进1名知识图谱架构师（有企业级图谱落地经验）；② 与高校合作开展知识图谱共建项目，借助外部智力",
  },
];

// ---- 偏差池 ----
const deviationItems = [
  {
    hypothesisName: "管道完整性管理域（L2）",
    hypothesisDetail: "假设管道失效率≤0.15次/千公里·年，预计数字化后可达成",
    currentFinding: "实际失效率为0.21次/千公里·年，老旧管线（服役>30年）占比40%，数字化覆盖率仅55%",
    consequence: "需重新评估管道数字化投资的优先级与预算模型",
  },
  {
    hypothesisName: "机采井智能工况诊断（L3）",
    hypothesisDetail: "假设CNN模型可覆盖全部14种常见工况，准确率≥95%",
    currentFinding: "实际仅覆盖12种工况，深井泵工况（泵深>3000m）识别准确率仅78%，漏检率偏高",
    consequence: "深井泵工况需单独训练模型，增加标注样本2000+条",
  },
  {
    hypothesisName: "炼化APC先进控制（关联L2-6）",
    hypothesisDetail: "假设APC投用率可达90%以上",
    currentFinding: "实际投用率仅63%，主要瓶颈是装置运行工况波动大，模型频繁失效需人工复位",
    consequence: "需引入自适应APC（AAPC）或实时优化(RTO)替代传统DMC算法",
  },
];

// ============================================================
// 组件
// ============================================================

/** 五维健康雷达图卡片 */
function FiveDimRadar({ health }: { health: FiveDimHealth }) {
  const dims = [
    { key: "L5_数字意识" as const, label: "数字意识", short: "意识", color: "var(--info)" },
    { key: "L4_数字神经" as const, label: "数字神经", short: "神经", color: "var(--accent)" },
    { key: "L3_数字器官" as const, label: "数字器官", short: "器官", color: "var(--success)" },
    { key: "L2_数字血液" as const, label: "数字血液", short: "血液", color: "var(--warn)" },
    { key: "L1_数字骨架" as const, label: "数字骨架", short: "骨架", color: "var(--danger)" },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 4 }}>
        五维健康观测
      </div>
      {dims.map(d => (
        <div key={d.key} style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: d.color, width: 56, flexShrink: 0 }}>{d.label}</span>
          <div style={{ flex: 1, height: 6, background: "var(--bg-3)", borderRadius: 3, overflow: "hidden" }}>
            <div style={{
              width: `${(health[d.key].score / 5) * 100}%`, height: "100%",
              background: health[d.key].score <= 2 ? "var(--danger)" : health[d.key].score === 3 ? "var(--warn)" : "var(--success)",
              borderRadius: 3, transition: "width 400ms",
            }} />
          </div>
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ink)", width: 20, textAlign: "right" }}>{health[d.key].score}/5</span>
        </div>
      ))}
    </div>
  );
}

export default function BusinessMapPage() {
  const [selectedProject, setSelectedProject] = useState(MOCK_PROJECTS[0].id);
  const [subView, setSubView] = useState<"hypothesis" | "current" | "deviation" | "preanalysis" | "health">("hypothesis");
  const [expandedL1, setExpandedL1] = useState<Set<string>>(new Set(l1Nodes.map(n => n.id)));
  const [expandedL2, setExpandedL2] = useState<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<MapNode | null>(null);

  const toggleL1 = (id: string) => {
    setExpandedL1(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  };
  const toggleL2 = (id: string) => {
    setExpandedL2(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  };

  const filteredL2 = subView === "current"
    ? l2Nodes.filter(n => n.mapType === "current" || n.verificationStatus)
    : l2Nodes;

  const childL2 = (parentId: string) => filteredL2.filter(n => n.parentId === parentId);
  const childL3 = (parentId: string) => l3Nodes.filter(n => n.parentId === parentId);
  const childL4 = (parentId: string) => l4Nodes.filter(n => n.parentId === parentId);
  const supportL2 = filteredL2.filter(n => n.parentId === null);

  const getStatusColor = (s?: string) => {
    if (s === "成立") return "var(--success)";
    if (s === "部分成立") return "var(--warn)";
    if (s === "推翻") return "var(--danger)";
    return "var(--ink-3)";
  };

  const getConfidenceTag = (level: string) => {
    if (level === "高") return { tone: "success" as const, label: "高置信" };
    if (level === "中") return { tone: "warn" as const, label: "中置信" };
    return { tone: "neutral" as const, label: "低置信" };
  };

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
        {[
          ["L1", l1Nodes.length, "var(--accent)"],
          ["L2", l2Nodes.length, "var(--info)"],
          ["L3", l3Nodes.length, "var(--success)"],
          ["L4", l4Nodes.length, "var(--warn)"],
        ].map(([label, count, color]) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: color, flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{label}: <b style={{ color: "var(--ink)" }}>{String(count)}</b></span>
          </div>
        ))}
        <span style={{ fontSize: 12, color: "var(--success)", fontWeight: 500 }}>
          ✅ 已验证 3/13 (23%)
        </span>
      </div>

      {/* 子视图 Tab（新增：前置分析、五维健康） */}
      <div style={{ padding: "0 20px", borderBottom: "1px solid var(--line)", background: "var(--bg)", display: "flex", gap: 0, flexShrink: 0 }}>
        {([
          ["hypothesis", "🗺️ 假设地图"],
          ["current", "📋 现状地图"],
          ["deviation", `⚠️ 偏差池 (${deviationItems.length})`],
          ["preanalysis", "🔍 前置分析"],
          ["health", "📊 五维健康"],
        ] as const).map(([key, label]) => (
          <button key={key} onClick={() => setSubView(key)}
            style={{
              padding: "10px 16px", background: "transparent", border: "none",
              borderBottom: subView === key ? "2px solid var(--accent)" : "2px solid transparent",
              color: subView === key ? "var(--accent)" : "var(--ink-2)",
              fontSize: 13, fontWeight: subView === key ? 600 : 400,
              cursor: "pointer", fontFamily: "inherit", transition: "color 120ms, border-color 120ms",
            }}>
            {label}
          </button>
        ))}
      </div>

      {/* 主内容 */}
      <div style={{ flex: 1, overflow: "auto", padding: 20, display: "flex", gap: 20 }}>
        {/* 左侧：地图树 / 特殊视图 */}
        <Card style={{ flex: 1, padding: 16, overflow: "auto" }}>
          {subView === "deviation" ? (
            // 偏差池视图
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 4 }}>
                以下节点假设与现状存在显著偏差，需重点关注：
              </div>
              {deviationItems.map((d, i) => (
                <div key={i} style={{
                  padding: 14, background: "var(--danger-soft)", border: "1px solid var(--danger)",
                  borderRadius: 10, fontSize: 13,
                }}>
                  <div style={{ fontWeight: 600, color: "var(--danger)", marginBottom: 8, fontSize: 14 }}>{d.hypothesisName}</div>
                  <div style={{ marginBottom: 6 }}>
                    <span style={{ fontWeight: 500, color: "var(--ink-2)" }}>📐 假设：</span>
                    <span style={{ color: "var(--ink-2)" }}>{d.hypothesisDetail}</span>
                  </div>
                  <div style={{ marginBottom: 6 }}>
                    <span style={{ fontWeight: 500, color: "var(--ink)" }}>🔍 现状：</span>
                    <span style={{ color: "var(--ink)" }}>{d.currentFinding}</span>
                  </div>
                  <div style={{ borderTop: "1px solid var(--danger-soft)", paddingTop: 8, fontSize: 12, color: "var(--ink-2)" }}>
                    <span style={{ fontWeight: 500 }}>📌 影响：</span>{d.consequence}
                  </div>
                </div>
              ))}
            </div>
          ) : subView === "preanalysis" ? (
            // 前置分析视图
            <div style={{ display: "flex", flexDirection: "column", gap: 16, fontSize: 13 }}>
              <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)", marginBottom: 8 }}>产业环境与战略定位分析</div>
              <div style={{ padding: 14, background: "var(--bg-2)", borderRadius: 10, border: "1px solid var(--line)" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)", marginBottom: 6 }}>🏭 行业价值链</div>
                <div style={{ color: "var(--ink-2)", lineHeight: 1.7 }}>{preAnalysis.industryValueChain}</div>
              </div>
              <div style={{ padding: 14, background: "var(--bg-2)", borderRadius: 10, border: "1px solid var(--line)" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)", marginBottom: 6 }}>📊 客户行业地位</div>
                <div style={{ color: "var(--ink-2)", lineHeight: 1.7 }}>{preAnalysis.customerPosition}</div>
              </div>
              <div style={{ padding: 14, background: "var(--bg-2)", borderRadius: 10, border: "1px solid var(--line)" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)", marginBottom: 6 }}>📈 行业趋势与变化</div>
                <div style={{ color: "var(--ink-2)", lineHeight: 1.7 }}>{preAnalysis.industryTrends}</div>
              </div>
              <div style={{ padding: 14, background: "var(--bg-2)", borderRadius: 10, border: "1px solid var(--line)" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)", marginBottom: 6 }}>🎯 客户战略定位</div>
                <div style={{ color: "var(--ink-2)", lineHeight: 1.7 }}>{preAnalysis.strategicPositioning}</div>
              </div>
              <div style={{ padding: 14, background: "var(--accent-soft)", borderRadius: 10, border: "1px solid var(--accent)" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)", marginBottom: 6 }}>⚡ 数字化驱动力（与L1关联）</div>
                <div style={{ color: "var(--ink)", lineHeight: 1.7 }}>{preAnalysis.digitalizationDrivers}</div>
              </div>
            </div>
          ) : subView === "health" ? (
            // 五维健康总览视图
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)" }}>公司级五维健康总览（L1层）</div>
              <FiveDimRadar health={fiveDimL1} />
              <div style={{ marginTop: 12, borderTop: "1px solid var(--line)", paddingTop: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-3)", marginBottom: 12, textTransform: "uppercase" }}>
                  各价值链环节五维健康对比
                </div>
                <div style={{ overflow: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                    <thead>
                      <tr style={{ background: "var(--bg-2)", borderBottom: "2px solid var(--line)" }}>
                        <th style={{ padding: "8px 12px", textAlign: "left", fontWeight: 700, color: "var(--ink-3)" }}>价值链环节</th>
                        {["L5意识", "L4神经", "L3器官", "L2血液", "L1骨架"].map(h => (
                          <th key={h} style={{ padding: "8px 8px", textAlign: "center", fontWeight: 700, color: "var(--ink-3)" }}>{h}</th>
                        ))}
                        <th style={{ padding: "8px 12px", textAlign: "center", fontWeight: 700, color: "var(--ink-3)" }}>平均</th>
                      </tr>
                    </thead>
                    <tbody>
                      {l1Nodes.map(l1 => {
                        const dims = [l1.fiveDimHealth!.L5_数字意识.score, l1.fiveDimHealth!.L4_数字神经.score, l1.fiveDimHealth!.L3_数字器官.score, l1.fiveDimHealth!.L2_数字血液.score, l1.fiveDimHealth!.L1_数字骨架.score];
                        const avg = (dims.reduce((a, b) => a + b, 0) / 5).toFixed(1);
                        return (
                          <tr key={l1.id} style={{ borderBottom: "1px solid var(--line)", cursor: "pointer" }}
                            onClick={() => { setSelectedNode(l1); setSubView("hypothesis"); }}>
                            <td style={{ padding: "8px 12px", fontWeight: 500 }}>{l1.name}</td>
                            {dims.map((s, i) => (
                              <td key={i} style={{ padding: "8px 8px", textAlign: "center" }}>
                                <span style={{
                                  padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600,
                                  background: s <= 2 ? "var(--danger-soft)" : s === 3 ? "var(--warn-soft)" : "var(--success-soft)",
                                  color: s <= 2 ? "var(--danger)" : s === 3 ? "var(--warn)" : "var(--success)",
                                }}>{s}</span>
                              </td>
                            ))}
                            <td style={{ padding: "8px 12px", textAlign: "center", fontWeight: 700 }}>{avg}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : (
            // 假设/现状地图树
            <div style={{ fontSize: 13 }}>
              {l1Nodes.map(l1 => (
                <div key={l1.id} style={{ marginBottom: 4 }}>
                  {/* L1 节点 */}
                  <div onClick={() => { toggleL1(l1.id); setSelectedNode(l1); }}
                    style={{
                      display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
                      background: selectedNode?.id === l1.id ? "var(--accent-soft)" : "var(--bg-2)",
                      border: `1px solid ${selectedNode?.id === l1.id ? "var(--accent)" : "var(--line)"}`,
                      borderRadius: 10, cursor: "pointer", transition: "background 120ms", marginBottom: 3,
                    }}>
                    <I.ChevronRight size={12} style={{
                      color: "var(--ink-4)", transform: expandedL1.has(l1.id) ? "rotate(90deg)" : "none",
                      transition: "transform 160ms", flexShrink: 0,
                    }} />
                    <span style={{
                      padding: "2px 8px", borderRadius: 5, fontSize: 10, fontWeight: 700,
                      background: "var(--accent-soft)", color: "var(--accent)", flexShrink: 0,
                    }}>L1</span>
                    <span style={{ fontWeight: 600, fontSize: 14, flex: 1 }}>{l1.name}</span>
                    <Tag tone={getConfidenceTag(l1.confidenceLevel).tone} dot>{getConfidenceTag(l1.confidenceLevel).label}</Tag>
                    {l1.mapType === "current" && <Tag tone="info">现状</Tag>}
                  </div>

                  {/* L2 子节点 */}
                  {expandedL1.has(l1.id) && (
                    <div style={{ marginLeft: 24, borderLeft: "2px solid var(--line)", paddingLeft: 16, marginBottom: 8 }}>
                      {childL2(l1.id).map(l2 => (
                        <div key={l2.id} style={{ marginTop: 4 }}>
                          <div onClick={() => { toggleL2(l2.id); setSelectedNode(l2); }}
                            style={{
                              display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
                              background: selectedNode?.id === l2.id ? "var(--info-soft)" : "transparent",
                              border: `1px solid ${selectedNode?.id === l2.id ? "var(--info)" : "transparent"}`,
                              borderRadius: 8, cursor: "pointer", transition: "background 120ms",
                            }}>
                            <I.ChevronRight size={10} style={{
                              color: "var(--ink-4)", transform: expandedL2.has(l2.id) ? "rotate(90deg)" : "none",
                              transition: "transform 160ms", flexShrink: 0,
                            }} />
                            <span style={{
                              padding: "1px 6px", borderRadius: 4, fontSize: 9, fontWeight: 700,
                              background: "var(--info-soft)", color: "var(--info)", flexShrink: 0,
                            }}>L2</span>
                            <span style={{ fontWeight: 500, fontSize: 13, flex: 1 }}>{l2.name}</span>
                            <span style={{ fontSize: 10, color: "var(--ink-3)", padding: "1px 6px", borderRadius: 999, background: "var(--bg-3)" }}>{l2.domainType}</span>
                            {l2.verificationStatus && (
                              <span style={{ fontSize: 10, color: getStatusColor(l2.verificationStatus), fontWeight: 500 }}>
                                {l2.verificationStatus === "成立" ? "✅ 成立" : l2.verificationStatus === "部分成立" ? "⚠️ 部分成立" : l2.verificationStatus}
                              </span>
                            )}
                          </div>
                          {/* L3 子节点 */}
                          {expandedL2.has(l2.id) && childL3(l2.id).map(l3 => (
                            <div key={l3.id} style={{ marginLeft: 28, marginTop: 3 }}>
                              <div onClick={() => setSelectedNode(l3)}
                                style={{
                                  display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
                                  background: selectedNode?.id === l3.id ? "var(--success-soft)" : "transparent",
                                  border: `1px solid ${selectedNode?.id === l3.id ? "var(--success)" : "transparent"}`,
                                  borderRadius: 7, cursor: "pointer", transition: "background 120ms",
                                }}>
                                <span style={{
                                  padding: "1px 6px", borderRadius: 4, fontSize: 9, fontWeight: 700,
                                  background: "var(--success-soft)", color: "var(--success)", flexShrink: 0,
                                }}>L3</span>
                                <span style={{ fontSize: 12, fontWeight: 500, flex: 1 }}>{l3.name}</span>
                                {l3.verificationStatus && (
                                  <span style={{ fontSize: 10, color: getStatusColor(l3.verificationStatus), fontWeight: 500 }}>
                                    {l3.verificationStatus}
                                  </span>
                                )}
                                <span style={{ fontSize: 10, color: "var(--ink-3)" }}>{l3.aiOpportunity?.substring(0, 28)}...</span>
                              </div>
                              {/* L4 子节点 */}
                              {childL4(l3.id).map(l4 => (
                                <div key={l4.id} onClick={() => setSelectedNode(l4)}
                                  style={{
                                    display: "flex", alignItems: "center", gap: 8, padding: "5px 10px", marginLeft: 24,
                                    background: selectedNode?.id === l4.id ? "var(--warn-soft)" : "transparent",
                                    border: `1px solid ${selectedNode?.id === l4.id ? "var(--warn)" : "transparent"}`,
                                    borderRadius: 6, cursor: "pointer", transition: "background 120ms",
                                  }}>
                                  <span style={{
                                    padding: "1px 6px", borderRadius: 4, fontSize: 9, fontWeight: 700,
                                    background: "var(--warn-soft)", color: "var(--warn)", flexShrink: 0,
                                  }}>L4</span>
                                  <span style={{ fontSize: 11, fontWeight: 500, flex: 1 }}>{l4.name}</span>
                                  <span style={{ fontSize: 10, color: "var(--ink-3)" }}>{l4.capabilityType}</span>
                                  <span style={{ fontSize: 10, fontWeight: 600, color: l4.masteryLevel === "缺口" || l4.masteryLevel === "稀缺" ? "var(--danger)" : "var(--ink-2)" }}>
                                    {l4.masteryLevel}
                                  </span>
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

              {/* 横向支撑域 */}
              <div style={{ marginTop: 20, borderTop: "2px dashed var(--line)", paddingTop: 16 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 10 }}>
                  横向支撑域
                </div>
                {supportL2.map(l2 => (
                  <div key={l2.id} style={{ marginTop: 4 }}>
                    <div onClick={() => { toggleL2(l2.id); setSelectedNode(l2); }}
                      style={{
                        display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
                        background: selectedNode?.id === l2.id ? "var(--info-soft)" : "transparent",
                        border: `1px solid ${selectedNode?.id === l2.id ? "var(--info)" : "transparent"}`,
                        borderRadius: 8, cursor: "pointer", transition: "background 120ms",
                      }}>
                      <I.ChevronRight size={10} style={{
                        color: "var(--ink-4)", transform: expandedL2.has(l2.id) ? "rotate(90deg)" : "none",
                        transition: "transform 160ms", flexShrink: 0,
                      }} />
                      <span style={{
                        padding: "1px 6px", borderRadius: 4, fontSize: 9, fontWeight: 700,
                        background: l2.domainType === "职能域" ? "var(--warn-soft)" : "var(--info-soft)",
                        color: l2.domainType === "职能域" ? "var(--warn)" : "var(--info)", flexShrink: 0,
                      }}>L2</span>
                      <span style={{ fontWeight: 500, fontSize: 13, flex: 1 }}>{l2.name}</span>
                      <span style={{ fontSize: 10, color: "var(--ink-3)", padding: "1px 6px", borderRadius: 999, background: "var(--bg-3)" }}>{l2.domainType}</span>
                    </div>
                    {expandedL2.has(l2.id) && (
                      <div style={{ marginLeft: 28, marginTop: 3 }}>
                        {childL3(l2.id).map(l3 => (
                          <div key={l3.id} onClick={() => setSelectedNode(l3)}
                            style={{
                              display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
                              background: selectedNode?.id === l3.id ? "var(--success-soft)" : "transparent",
                              border: `1px solid ${selectedNode?.id === l3.id ? "var(--success)" : "transparent"}`,
                              borderRadius: 7, cursor: "pointer", marginBottom: 2,
                            }}>
                            <span style={{ padding: "1px 6px", borderRadius: 4, fontSize: 9, fontWeight: 700, background: "var(--success-soft)", color: "var(--success)" }}>L3</span>
                            <span style={{ fontSize: 12, fontWeight: 500, flex: 1 }}>{l3.name}</span>
                          </div>
                        ))}
                        {childL3(l2.id).flatMap(l3 => childL4(l3.id)).map(l4 => (
                          <div key={l4.id} onClick={() => setSelectedNode(l4)}
                            style={{
                              display: "flex", alignItems: "center", gap: 8, padding: "5px 10px", marginLeft: 24,
                              background: selectedNode?.id === l4.id ? "var(--warn-soft)" : "transparent",
                              border: `1px solid ${selectedNode?.id === l4.id ? "var(--warn)" : "transparent"}`,
                              borderRadius: 6, cursor: "pointer",
                            }}>
                            <span style={{ padding: "1px 6px", borderRadius: 4, fontSize: 9, fontWeight: 700, background: "var(--warn-soft)", color: "var(--warn)" }}>L4</span>
                            <span style={{ fontSize: 11, fontWeight: 500, flex: 1 }}>{l4.name}</span>
                            <span style={{ fontSize: 10, fontWeight: 600, color: (l4.masteryLevel === "缺口" || l4.masteryLevel === "稀缺") ? "var(--danger)" : "var(--ink-2)" }}>{l4.masteryLevel}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>

        {/* 右侧详情面板（根据 subView 显示不同内容） */}
        {subView === "preanalysis" ? (
          <Card style={{ width: 300, padding: 20, flexShrink: 0, overflow: "auto" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 12 }}>
              📋 分析维度说明
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12, fontSize: 12, color: "var(--ink-2)", lineHeight: 1.6 }}>
              <div>前置分析回答：<b>为什么客户当前的战略是这样？为什么数字化是它的关键抓手？</b></div>
              <div>五个维度层层递进：行业价值链 → 客户地位 → 行业趋势 → 战略定位 → 数字化驱动力</div>
              <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12, color: "var(--ink-3)" }}>
                与L1地图的关系：数字化驱动力直接关联L1五维健康中的"数字意识"和"数字神经"维度，
                为后续L1价值链健康诊断提供战略上下文。
              </div>
            </div>
          </Card>
        ) : subView === "health" ? (
          <Card style={{ width: 320, padding: 20, flexShrink: 0, overflow: "auto" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", marginBottom: 12 }}>
              📖 五维健康解读
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 12, color: "var(--ink-2)", lineHeight: 1.6 }}>
              {[
                ["L5 数字意识", "战略是否分解到各价值链环节？IT投资与业务战略是否匹配？", "var(--info)"],
                ["L4 数字神经", "跨环节流程是否顺畅？协同效率如何？变更是否可控？", "var(--accent)"],
                ["L3 数字器官", "核心IT系统是否覆盖各环节？系统间是否集成？用户是否愿意用？", "var(--success)"],
                ["L2 数字血液", "跨价值链关键数据是否准确、及时、共享？", "var(--warn)"],
                ["L1 数字骨架", "基础设施是否弹性、经济、可持续？", "var(--danger)"],
              ].map(([title, desc, color]) => (
                <div key={title} style={{ padding: 10, background: "var(--bg-2)", borderRadius: 8, borderLeft: `3px solid ${color}` }}>
                  <div style={{ fontWeight: 600, color: color, marginBottom: 4 }}>{title}</div>
                  <div style={{ fontSize: 11 }}>{desc}</div>
                </div>
              ))}
              <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12, fontSize: 11, color: "var(--ink-3)" }}>
                评分标准：5分=行业领先 / 3分=行业平均 / 1分=严重不足。点击左侧表格行可跳转查看该价值链环节详情。
              </div>
            </div>
          </Card>
        ) : (
          <Card style={{ width: 350, padding: 20, flexShrink: 0, overflow: "auto" }}>
            {selectedNode ? (
              <div style={{ fontSize: 13 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                  <span style={{
                    padding: "2px 8px", borderRadius: 5, fontSize: 10, fontWeight: 700,
                    background: selectedNode.level === "L1" ? "var(--accent-soft)" :
                      selectedNode.level === "L2" ? "var(--info-soft)" :
                      selectedNode.level === "L3" ? "var(--success-soft)" : "var(--warn-soft)",
                    color: selectedNode.level === "L1" ? "var(--accent)" :
                      selectedNode.level === "L2" ? "var(--info)" :
                      selectedNode.level === "L3" ? "var(--success)" : "var(--warn)",
                  }}>{selectedNode.level}</span>
                  <span style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--serif)" }}>{selectedNode.name}</span>
                </div>

                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
                  <Tag tone={getConfidenceTag(selectedNode.confidenceLevel).tone}>{getConfidenceTag(selectedNode.confidenceLevel).label}</Tag>
                  <Tag tone="neutral">{selectedNode.sourceType}</Tag>
                  {selectedNode.mapType === "current" && <Tag tone="info">现状地图</Tag>}
                  {selectedNode.verificationStatus && (
                    <Tag tone={selectedNode.verificationStatus === "成立" ? "success" : selectedNode.verificationStatus === "部分成立" ? "warn" : "danger"}>
                      {selectedNode.verificationStatus}
                    </Tag>
                  )}
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {/* === L1 fields === */}
                  {selectedNode.coreActivities && <Field label="核心业务活动" value={selectedNode.coreActivities} />}
                  {selectedNode.capabilityChain && <Field label="能力链" value={selectedNode.capabilityChain} />}
                  {selectedNode.itSystems && <Field label="IT系统" value={selectedNode.itSystems} />}
                  {selectedNode.organization && <Field label="组织" value={selectedNode.organization} />}

                  {/* === L2 fields === */}
                  {selectedNode.domainType && <Field label="域类型" value={selectedNode.domainType} />}
                  {selectedNode.domainGoal && <Field label="域目标(SMART)" value={selectedNode.domainGoal} />}
                  {selectedNode.valueStream && <Field label="价值流" value={selectedNode.valueStream} />}
                  {selectedNode.subScenarios && <Field label="子场景" value={selectedNode.subScenarios} />}
                  {selectedNode.coreCapabilities && <Field label="核心能力" value={selectedNode.coreCapabilities} />}
                  {selectedNode.supportITSystems && <Field label="支撑IT系统" value={selectedNode.supportITSystems} />}
                  {selectedNode.keyOrganizations && <Field label="关键组织/岗位" value={selectedNode.keyOrganizations} />}
                  {selectedNode.keyDataEntities && <Field label="关键数据实体" value={selectedNode.keyDataEntities} />}
                  {selectedNode.disconnectionPoints && (
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--danger)", marginBottom: 4, marginTop: 4 }}>主要脱节点</div>
                      <div style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.6, background: "var(--danger-soft)", padding: 8, borderRadius: 6 }}>{selectedNode.disconnectionPoints}</div>
                    </div>
                  )}

                  {/* === L3 fields === */}
                  {selectedNode.businessObjective && <Field label="业务目标(SMART)" value={selectedNode.businessObjective} />}
                  {selectedNode.businessProcess && <Field label="业务流程" value={selectedNode.businessProcess} />}
                  {selectedNode.keyActivities && <Field label="关键活动" value={selectedNode.keyActivities} />}
                  {selectedNode.capabilityUnits && <Field label="能力单元" value={selectedNode.capabilityUnits} highlight />}
                  {selectedNode.dataFlow && <Field label="数据流" value={selectedNode.dataFlow} />}
                  {selectedNode.positions && <Field label="岗位" value={selectedNode.positions} />}
                  {selectedNode.supportSystems && <Field label="支撑系统" value={selectedNode.supportSystems} />}
                  {selectedNode.painPoints && (
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--danger)", marginBottom: 4, marginTop: 4 }}>痛点</div>
                      <div style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.6, background: "var(--danger-soft)", padding: 8, borderRadius: 6 }}>{selectedNode.painPoints}</div>
                    </div>
                  )}
                  {/* 业务本体抽取（L3核心） */}
                  {selectedNode.ontologyExtraction && (
                    <div style={{ marginTop: 8, border: "1px solid var(--accent)", borderRadius: 8, overflow: "hidden" }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: "#FFFCF5", background: "var(--accent)", padding: "6px 10px" }}>
                        🧠 业务本体抽取（先本体后AI）
                      </div>
                      <div style={{ padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                        <div>
                          <div style={{ fontSize: 10, fontWeight: 600, color: "var(--info)" }}>实体 (Entities)</div>
                          <div style={{ fontSize: 11, color: "var(--ink-2)", lineHeight: 1.5 }}>{selectedNode.ontologyExtraction.entities}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: 10, fontWeight: 600, color: "var(--success)" }}>关系 (Relations)</div>
                          <div style={{ fontSize: 11, color: "var(--ink-2)", lineHeight: 1.5 }}>{selectedNode.ontologyExtraction.relations}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: 10, fontWeight: 600, color: "var(--warn)" }}>规则 (Rules)</div>
                          <div style={{ fontSize: 11, color: "var(--ink-2)", lineHeight: 1.5 }}>{selectedNode.ontologyExtraction.rules}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: 10, fontWeight: 600, color: "var(--danger)" }}>动作 (Actions)</div>
                          <div style={{ fontSize: 11, color: "var(--ink-2)", lineHeight: 1.5 }}>{selectedNode.ontologyExtraction.actions}</div>
                        </div>
                      </div>
                    </div>
                  )}
                  {selectedNode.aiOpportunity && <Field label="AI 机会点" value={selectedNode.aiOpportunity} highlight />}

                  {/* === L4 fields === */}
                  {selectedNode.l3KeyActivity && <Field label="关联L3关键活动" value={selectedNode.l3KeyActivity} />}
                  {selectedNode.capabilityUnitName && <Field label="能力单元名称" value={selectedNode.capabilityUnitName} highlight />}
                  {selectedNode.capabilityType && <Field label="能力类型" value={selectedNode.capabilityType} />}
                  {selectedNode.capabilityDetail && <Field label="能力详细描述" value={selectedNode.capabilityDetail} />}
                  {selectedNode.masteryLevel && <Field label="掌握程度要求" value={selectedNode.masteryLevel} highlight={selectedNode.masteryLevel === "缺口" || selectedNode.masteryLevel?.includes("稀缺")} />}
                  {selectedNode.associatedPosition && <Field label="关联岗位" value={selectedNode.associatedPosition} />}
                  {selectedNode.currentRate && <Field label="当前能力达标率" value={selectedNode.currentRate} />}
                  {selectedNode.talentGap && (
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--warn)", marginBottom: 4, marginTop: 4 }}>人才差距与建议</div>
                      <div style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.6, background: "var(--warn-soft)", padding: 8, borderRadius: 6 }}>{selectedNode.talentGap}</div>
                    </div>
                  )}

                  {/* 五维健康（L1/L2/L3通用） */}
                  {selectedNode.fiveDimHealth && (
                    <div style={{ marginTop: 8, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
                      <FiveDimRadar health={selectedNode.fiveDimHealth} />
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div style={{ fontSize: 13, color: "var(--ink-3)", textAlign: "center", paddingTop: 40 }}>
                👈 点击左侧树节点<br />查看详情
              </div>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}

// 内联字段展示组件
function Field({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, color: highlight ? "var(--accent)" : "var(--ink-3)", marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.55 }}>{value}</div>
    </div>
  );
}
