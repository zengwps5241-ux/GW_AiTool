# 业务候选字段契约

本文档用于约束 AI 工作流从“生成候选”到“入库并在业务版块渲染”的数据契约。后续重构 skill、plugin、MCP 工具、候选状态表、Markdown renderer 和业务页面时，应以本文档为对齐基准。

## 1. 基本原则

### 1.1 候选定义

“候选”只指特定业务工作流产物，不包括普通聊天内容、普通文件、临时分析文档。

可产生候选的工作流包括：

- 生成假设地图
- 整理访谈纪要 / 拜访记录
- 生成角色卡
- 生成拜访前方案
- 验证假设（后续实现）

普通对话即使与项目相关，也不应自动生成业务候选。

### 1.2 触发边界

业务候选只能在以下场景产生：

- 用户显式调用 command 或点击工作流入口。
- 当前会话已处于某个未完成业务工作流中，用户继续确认、提问或提出修改意见。

普通聊天状态下不应挂载或允许调用业务候选写入工具。

### 1.3 唯一事实源

候选的唯一事实源是后端维护的候选状态，不是 Markdown 文件，也不是对话历史。

对于长产物，尤其是假设地图，候选不应由 Agent 一次性生成完整大 JSON。应采用阶段级候选片段：

```text
工作流阶段内容
→ Agent 提交阶段结构化片段
→ 后端保存候选状态
→ 后端校验
→ 后端渲染 Markdown/页面预览
→ 用户确认或修改
```

Markdown 是候选状态的派生视图。用户看到的文档预览必须由候选状态渲染，不能由 Agent 另行生成一份独立 Markdown。

### 1.4 字段命名

正式业务数据和候选结构化字段使用当前业务版块已读取的字段名，优先使用 camelCase 的 payload 字段。

中文字段名只用于 Markdown renderer 的展示标签，不作为入库字段名。

## 2. 通用候选结构

建议后续统一使用如下逻辑结构，可以用多表实现，也可以先用 JSONB 实现。

```json
{
  "candidateType": "hypothesis_map | stakeholder_card | visit_record | visit_plan | hypothesis_verification",
  "schemaVersion": "v1",
  "projectId": 1,
  "workflowId": 1,
  "status": "active | finalized | adopted | cancelled",
  "currentStage": "A",
  "businessData": {},
  "documentView": {},
  "validationReport": {
    "errors": [],
    "warnings": []
  }
}
```

通用字段含义：

| 字段 | 必填 | 说明 |
| :--- | :--- | :--- |
| candidateType | 是 | 候选类型 |
| schemaVersion | 是 | 候选 schema 版本 |
| projectId | 是 | 所属项目 |
| workflowId | 是 | 所属工作流实例 |
| status | 是 | 候选状态 |
| currentStage | 否 | 分阶段工作流当前阶段 |
| businessData | 是 | 入库事实源 |
| documentView | 否 | 文档渲染辅助结构 |
| validationReport | 是 | 后端校验结果 |

## 3. 假设地图候选契约

### 3.1 工作流阶段

假设地图应分阶段生成和确认：

| 阶段 | 名称 | 是否直接入 BusinessMapObject |
| :--- | :--- | :--- |
| A | 前置分析与公开来源 | 否，进入 pre-analysis 或候选文档视图 |
| B | L1/L2 业务骨架 | 是 |
| C | L3 关键场景 | 是 |
| D | L4 能力/人才地图 | 是 |
| E | IT 大健康观测与收口 | 部分进入 payload / 文档视图，是否单独建模待定 |

### 3.2 节点通用字段

候选阶段使用 `tempId` 和 `parentTempId` 表达层级关系。正式入库时由后端转换为真实 `id` 和 `parent_id`。

```json
{
  "tempId": "L2-001",
  "level": "L2",
  "name": "招聘交付管理",
  "parentTempId": "L1-001",
  "mapType": "hypothesis",
  "verificationStatus": "未验证",
  "confidenceLevel": "中",
  "sourceType": "搜索采集",
  "sources": [],
  "payload": {}
}
```

| 字段 | 必填 | 说明 |
| :--- | :--- | :--- |
| tempId | 是 | 候选内临时 ID，同一候选内唯一 |
| level | 是 | L1/L2/L3/L4 |
| name | 是 | 节点名称 |
| parentTempId | L1 否，其余是 | 父级临时 ID |
| mapType | 是 | 固定为 hypothesis |
| verificationStatus | 是 | 假设地图默认未验证 |
| confidenceLevel | 是 | 高/中/低 |
| sourceType | 是 | 搜索采集/用户上传/行业模板/模型知识/混合 |
| sources | 否 | 来源摘要 |
| payload | 是 | 层级差异化字段 |

### 3.3 L1 payload

业务地图页面当前读取以下字段：

```json
{
  "coreActivities": [],
  "capabilityChain": [],
  "itSystems": [],
  "organization": [],
  "fiveDimHealth": {},
  "confidenceLevel": "中",
  "sourceType": "搜索采集"
}
```

| 字段 | 建议类型 | 展示含义 |
| :--- | :--- | :--- |
| coreActivities | string[] 或 string | 核心业务活动 |
| capabilityChain | string[] 或 string | 能力链 |
| itSystems | string[] 或 string | IT 系统 |
| organization | string[] 或 string | 组织 |
| fiveDimHealth | object | 五维健康，L1/L2/L3 通用 |
| confidenceLevel | string | 置信度 |
| sourceType | string | 来源类型 |

### 3.4 L2 payload

```json
{
  "domainGoal": "",
  "valueStream": [],
  "subScenarios": [],
  "coreCapabilities": [],
  "supportITSystems": [],
  "keyOrganizations": [],
  "keyDataEntities": [],
  "disconnectionPoints": [],
  "fiveDimHealth": {}
}
```

| 字段 | 建议类型 | 展示含义 |
| :--- | :--- | :--- |
| domainGoal | string | 域目标（SMART） |
| valueStream | string[] 或 string | 价值流 |
| subScenarios | string[] | 子场景 |
| coreCapabilities | string[] | 核心能力 |
| supportITSystems | string[] | 支撑 IT 系统 |
| keyOrganizations | string[] | 关键组织/岗位 |
| keyDataEntities | string[] | 关键数据实体 |
| disconnectionPoints | string[] | 主要脱节点/断点 |
| fiveDimHealth | object | 五维健康 |

### 3.5 L3 payload

```json
{
  "businessObjective": "",
  "businessProcess": [],
  "keyActivities": [],
  "capabilityUnits": [],
  "dataFlow": [],
  "positions": [],
  "supportSystems": [],
  "painPoints": [],
  "ontologyExtraction": {
    "entities": [],
    "relations": [],
    "rules": [],
    "actions": []
  },
  "aiOpportunity": "",
  "fiveDimHealth": {}
}
```

| 字段 | 建议类型 | 展示含义 |
| :--- | :--- | :--- |
| businessObjective | string | 业务目标（SMART） |
| businessProcess | string[] 或 string | 业务流程 |
| keyActivities | string[] | 关键活动 |
| capabilityUnits | string[] | 能力单元 |
| dataFlow | string[] 或 string | 数据流 |
| positions | string[] | 岗位 |
| supportSystems | string[] | 支撑系统 |
| painPoints | string[] | 痛点 |
| ontologyExtraction | object | 业务本体抽取 |
| aiOpportunity | string | AI 机会点 |
| fiveDimHealth | object | 五维健康 |

### 3.6 L4 payload

```json
{
  "l3KeyActivity": "",
  "capabilityUnitName": "",
  "capabilityType": "",
  "capabilityDetail": "",
  "masteryLevel": "",
  "associatedPosition": "",
  "currentRate": "",
  "talentGap": ""
}
```

| 字段 | 建议类型 | 展示含义 |
| :--- | :--- | :--- |
| l3KeyActivity | string | 关联 L3 关键活动 |
| capabilityUnitName | string | 能力单元名称 |
| capabilityType | string | 能力类型 |
| capabilityDetail | string | 能力详细描述 |
| masteryLevel | string | 掌握程度要求 |
| associatedPosition | string | 关联岗位/人才画像 |
| currentRate | string | 当前能力达标率 |
| talentGap | string | 人才差距与建议 |

### 3.7 fiveDimHealth

业务地图页面读取 `payload.fiveDimHealth`。键名应统一：

```json
{
  "L5_数字意识": { "score": 3, "desc": "说明" },
  "L4_数字神经": { "score": 3, "desc": "说明" },
  "L3_数字器官": { "score": 3, "desc": "说明" },
  "L2_数字血液": { "score": 3, "desc": "说明" },
  "L1_数字骨架": { "score": 3, "desc": "说明" }
}
```

约束：

- 只用于 L1/L2/L3。
- score 为 1-5 整数。
- desc 必须说明依据。
- 不得使用“战略/业务/技术/数据/组织”替代 IT 大健康五层。

### 3.8 入库转换

候选入库到 `BusinessMapObject` 时：

| 候选字段 | 正式字段 |
| :--- | :--- |
| level | level |
| name | name |
| parentTempId | parent_id，后端转换 |
| mapType | map_type |
| verificationStatus | verification_status |
| payload | payload |
| generatedByAI | generated_by_ai |

注意：页面当前部分位置读取 `payload.generatedByAI`，但正式模型已有 `generated_by_ai`。后续应统一改为读取顶层 `generated_by_ai`，避免重复字段。

## 4. 角色卡候选契约

### 4.1 顶层字段

```json
{
  "name": "",
  "position": "",
  "department": "",
  "reports_to": "",
  "contact_info": "",
  "role_type": "technical_evaluator",
  "decision_power": "技术把关",
  "objective_layer": {},
  "subjective_layer": {},
  "behaviors": []
}
```

| 字段 | 必填 | 说明 |
| :--- | :--- | :--- |
| name | 是 | 姓名或称谓 |
| position | 否 | 岗位 |
| department | 否 | 部门 |
| reports_to | 否 | 汇报对象 |
| contact_info | 否 | 联系方式 |
| role_type | 否 | 角色类型枚举 |
| decision_power | 否 | 决策权 |
| objective_layer | 否 | 客观层 |
| subjective_layer | 否 | 主观层 |
| behaviors | 否 | 行为分析 |

### 4.2 role_type 枚举

必须使用后端 schema 支持的值：

| 值 | 含义 |
| :--- | :--- |
| economic_decision_maker | 经济决策者 |
| technical_evaluator | 技术评估者 |
| user | 使用者 |
| coach_supporter | 教练/支持者 |
| procurement_finance | 采购/财务 |

### 4.3 objective_layer

当前营销地图页面读取以下字段：

```json
{
  "education": "",
  "previousCompanies": "",
  "personality": "",
  "communicationPreference": "",
  "relationships": "",
  "historyWithUs": "",
  "historyWithCompetitor": ""
}
```

| 字段 | 展示含义 |
| :--- | :--- |
| education | 教育背景 |
| previousCompanies | 过往公司与年限 |
| personality | 性格特征 |
| communicationPreference | 沟通偏好 |
| relationships | 人际关系 |
| historyWithUs | 与我方历史合作 |
| historyWithCompetitor | 与竞品历史合作 |

### 4.4 subjective_layer

```json
{
  "stance": "观望",
  "confidence": "中",
  "explicitKPI": "待补充",
  "personalMotivation": "",
  "attitudeToUs": "",
  "attitudeToCompetitor": "",
  "engagement": 5,
  "influence": 5,
  "support": 5,
  "coreConcerns": "",
  "leverage": ""
}
```

| 字段 | 必填 | 说明 |
| :--- | :--- | :--- |
| stance | 否 | 支持/中立/反对/观望 |
| confidence | 否 | 高/中/低 |
| explicitKPI | 是 | 无依据时填“待补充” |
| personalMotivation | 否 | 隐性个人诉求 |
| attitudeToUs | 否 | 对我方方案态度 |
| attitudeToCompetitor | 否 | 对竞品态度 |
| engagement | 否 | 参与度，建议 1-10 |
| influence | 否 | 影响力，建议 1-10 |
| support | 否 | 支持度，建议 1-10 |
| coreConcerns | 否 | 核心顾虑 |
| leverage | 否 | 影响杠杆 |

`compositeScore` 和 `gradeLevel` 由后端服务计算，不要求 Agent 提交。

### 4.5 behaviors

```json
[
  {
    "observation": "",
    "interpretation": "",
    "suggestedAction": ""
  }
]
```

| 字段 | 说明 |
| :--- | :--- |
| observation | 观察 |
| interpretation | 解读 |
| suggestedAction | 建议动作 |

### 4.6 入库转换

候选入库到 `StakeholderCard` 时：

- 新建候选先进入候选状态。
- 用户确认后创建或更新正式角色卡。
- 若识别到疑似同人，应触发去重确认，不应直接重复建卡。
- `subjective_layer.engagement / influence / support` 应为数字，便于后端计算综合评分。

## 5. 拜访记录候选契约

### 5.1 顶层字段

```json
{
  "visit_date": "2026-07-16",
  "visit_type": "现场访谈",
  "participants_our": [],
  "participants_client": [],
  "unresolved_client_participants": [],
  "location": "",
  "duration": "",
  "summary": "",
  "next_steps": "",
  "key_takeaways": [],
  "related_card_ids": [],
  "evidence": []
}
```

| 字段 | 必填 | 说明 |
| :--- | :--- | :--- |
| visit_date | 否 | ISO 日期 |
| visit_type | 是 | 拜访类型枚举 |
| participants_our | 否 | 我方参与人姓名 |
| participants_client | 否 | 已匹配 StakeholderCard id |
| unresolved_client_participants | 否 | 未匹配客户参与人，候选阶段使用 |
| location | 否 | 地点 |
| duration | 否 | 时长 |
| summary | 否 | 摘要 |
| next_steps | 否 | 下一步行动 |
| key_takeaways | 否 | 要点 |
| related_card_ids | 否 | 关联角色卡 id |
| evidence | 否 | 候选证据，后续可单独入 EvidenceSource |

### 5.2 visit_type 枚举

必须使用：

- 现场访谈
- 电话沟通
- 视频会议
- 邮件
- 一句话记录

### 5.3 客户参与人处理

正式 `VisitRecord.participants_client` 当前为角色卡 ID 列表。Agent 在候选阶段可能只能识别姓名或称谓，因此候选允许：

```json
{
  "participants_client": [12, 15],
  "unresolved_client_participants": [
    { "name": "王主任", "department": "信息部", "position": "主任" }
  ]
}
```

采纳前或采纳时应处理未匹配人员：

- 匹配已有角色卡。
- 创建占位角色卡。
- 或保留在摘要/证据中，不写入 participants_client。

该策略需要产品确认。

### 5.4 evidence

候选阶段可抽取证据，但是否自动入 `EvidenceSource` 需要单独确认。

```json
[
  {
    "evidence_type": "客户原话",
    "strength": "中",
    "strength_note": "",
    "content": "",
    "source_role_id": null,
    "source_role_name": "",
    "related_hypothesis_id": null,
    "related_hypothesis_name": "",
    "implied_from_stance": null,
    "implied_to_stance": null
  }
]
```

字段必须对齐 `EvidenceSourceCreate`。

### 5.5 入库转换

候选入库到 `VisitRecord` 时：

| 候选字段 | 正式字段 |
| :--- | :--- |
| visit_date | visit_date |
| visit_type | visit_type |
| participants_our | participants_our |
| participants_client | participants_client |
| location | location |
| duration | duration |
| summary | summary |
| next_steps | next_steps |
| key_takeaways | key_takeaways |
| related_card_ids | related_card_ids |

`unresolved_client_participants` 不直接入 `VisitRecord`，需要转角色卡、忽略或写入摘要。

## 6. 拜访前方案候选契约

当前项目尚未确认拜访方案是否有正式业务表。暂定为文档型候选，不直接入业务地图、营销地图或拜访记录。

### 6.1 建议结构

```json
{
  "title": "",
  "visitContext": {
    "customerName": "",
    "projectName": "",
    "visitDate": "",
    "visitType": "",
    "targetStakeholders": []
  },
  "objectives": {
    "primary": "",
    "secondary": []
  },
  "stakeholderStrategy": [],
  "talkingPoints": [],
  "interviewQuestions": [],
  "materialsChecklist": {
    "toPrepare": [],
    "toRequest": []
  },
  "strategyRationale": ""
}
```

### 6.2 后续入库选择

需要产品确认：

- 如果拜访方案只是文档归档，则保存为项目文件/候选文档即可。
- 如果拜访方案要成为正式业务模块，应新增 `VisitPlan` 模型，并让候选字段对齐该模型。

## 7. 验证假设候选契约（待实现）

验证假设工作流应基于：

- `BusinessMapObject` 中 `map_type=hypothesis` 的节点。
- `EvidenceSource` 中关联假设的证据。
- 用户补充的现场信息。

建议候选结构：

```json
{
  "hypothesisUpdates": [
    {
      "hypothesisId": 1,
      "suggestedStatus": "成立",
      "reason": "",
      "evidenceIds": [],
      "confidence": "中"
    }
  ],
  "deviationCandidates": [
    {
      "sourceHypothesisId": 1,
      "name": "",
      "level": "L3",
      "parentHypothesisId": 2,
      "payload": {},
      "reason": ""
    }
  ]
}
```

该工作流复杂度较高，后续实现前应单独确认。

## 8. 后端校验规则

### 8.1 通用校验

- 无 active workflow 时拒绝写业务候选。
- workflow type 与工具类型不匹配时拒绝。
- projectId 与当前会话绑定项目不一致时拒绝。
- schemaVersion 不支持时拒绝。

### 8.2 假设地图校验

- `tempId` 唯一。
- L2/L3/L4 必须有合法 `parentTempId`。
- 层级关系必须是 L2→L1、L3→L2、L4→L3。
- L1/L2/L3 的 `fiveDimHealth` 键名和 score 合法。
- `mapType` 固定为 hypothesis。
- `verificationStatus` 默认未验证。
- 节点数量需符合业务边界，超出时进入扩展候选池或提示用户确认。

### 8.3 角色卡校验

- `role_type` 必须是枚举。
- `stance` 必须是支持/中立/反对/观望之一。
- `explicitKPI` 不得为空，无依据时填“待补充”。
- `engagement/influence/support` 若存在必须为数字。
- 同名/同部门/同岗位疑似同人时触发去重逻辑。

### 8.4 拜访记录校验

- `visit_type` 必须是枚举。
- `participants_client` 必须是当前项目内存在的角色卡 ID。
- 未匹配客户参与人必须放入 `unresolved_client_participants`。
- evidence 的 `evidence_type` 和 `strength` 必须是枚举。

## 9. 渲染规则

### 9.1 页面渲染

正式业务版块只读取正式业务表：

- 业务地图页面读取 `BusinessMapObject`。
- 营销地图页面读取 `StakeholderCard`。
- 拜访记录页面读取 `VisitRecord` 和 `EvidenceSource`。

候选页面或工作流预览读取 candidate state。

### 9.2 Markdown 渲染

Markdown 由后端 renderer 从候选状态生成。renderer 可以使用中文字段标签，但字段来源必须是本文档约定的结构化字段。

禁止 Agent 最后读取完整 Markdown 再转换 JSON，或读取完整 JSON 再自由重写 Markdown。

## 10. 待产品确认事项

1. 假设地图阶段 E 是否只作为文档视图，还是需要结构化入库到独立模块。
2. 拜访方案是否需要正式业务表。
3. 拜访记录中未匹配客户参与人的处理策略。
4. 证据是否在整理访谈纪要时自动入库，还是先作为候选内容等待用户确认。
5. 用户说“认可”时在不同阶段的语义：确认阶段、确认候选、还是最终入库。
6. 是否取消当前对话内待采纳卡片，改为纯工作流自然语言确认。
