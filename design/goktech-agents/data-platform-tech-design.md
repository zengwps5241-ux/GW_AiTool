# goktech-agents 数据工作台 技术方案

> 版本：v1.0
> 日期：2026-05-31
> 定位：售前/方案级技术方案
> 关联文档：《goktech-agent 产品需求文档（PRD）》（同目录 `goktech-agents-prd.md`）
> 覆盖需求：KR10（结构化数据接入工作台）、7.1.1「数据工作台」页面、7.2.1「数据工作台能力」、7.2.5/7.3.2 数据安全治理

---

## 1. 概述

数据工作台是 goktech-agent 平台「数据」主线的承载页面，职责是把客户现场的**非结构化与半结构化资料**快速转换为 **Agent 与知识工作台可消费的结构化数据**。它处在平台数据流的最上游：

```text
原始文件 ──► 数据工作台 ──► 结构化表(Supabase) ──► 知识工作台(RAG/图谱/本体) ──► Agent
（个人/团队空间）  解析·清洗·映射·脱敏           表查询              向量化·实体抽取        消费
```

### 1.1 核心职责（对齐 PRD 7.2.1）

| 能力 | PRD 要求 | 首版范围 |
| --- | --- | --- |
| 文档解析 | MinerU 非结构化解析，输出 Markdown + 图片包 | 必须支持 |
| ETL 工具 | 批量导入、清洗、字段映射、去重、脱敏、任务日志 | 核心导入与清洗流程 |
| 结构化数据后端 | Supabase 表/字段/权限/查询 | 必须支持 |
| 数据安全治理 | 脱敏、空间隔离、白名单、权限、审计日志 | 必须支持 |
| 工作空间文件管理 | 上传/下载/删除/建文件夹/批量导入 | 必须支持（与文件管理模块共用） |

### 1.2 设计取舍（关键决策）

| 决策点 | 选择 | 理由 |
| --- | --- | --- |
| 结构化后端 | Supabase（Postgres + PostgREST + RLS） | PRD 既定；自带 REST、行级权限、Auth，省去自建 CRUD 与鉴权层；私有化可自托管 |
| 文档解析部署 | MinerU **自托管为主 + 预留云 API** | 客户资料不出域是现场交付前提；接口抽象为 `ParserProvider`，可切云端 API 快速验证 |
| ETL/异步执行 | **轻量任务队列起步**（队列 + Worker），抽象 `JobRunner` | 首版只需「解析/清洗/导入」三类长任务，重型编排（Airflow/Dagster）过度；预留升级口 |
| 清洗/映射范式 | **配置驱动**（声明式规则 JSON），而非写代码 | 让数据角色无需编程即可配清洗与字段映射；规则可沉淀为团队资产复用 |
| 数据隔离粒度 | 空间（个人/团队）→ schema/前缀 → 行级 RLS 三层 | 满足「客户资料按空间和团队隔离」的硬约束，且可审计 |
| 状态权威 | 任务状态与表元数据由后端服务维护，非前端 | 解析/导入为长事务，需可恢复、可审计、可重试 |

---

## 2. 总体架构

### 2.1 架构分层

```text
交互层    数据工作台 Web UI
          ├─ 文件/数据源面板   选择个人/团队空间文件，批量选取
          ├─ 解析任务面板      MinerU 解析、进度、Markdown/图片包预览下载
          ├─ ETL 配置器        映射规则、清洗规则、脱敏规则（声明式，可视化配）
          ├─ 表管理器          Supabase 表/字段浏览、数据预览、查询
          └─ 任务日志          解析/清洗/导入任务的状态、行数、错误样本
              │  REST / WebSocket（任务进度流）
服务层    Data Platform Service（FastAPI）
          ├─ ParseService      调用 ParserProvider(MinerU)，产出 Markdown+资源包
          ├─ ETLService        读取规则 → 清洗/去重/脱敏/字段映射 → 落表
          ├─ SchemaService     Supabase 表/字段管理、DDL 生成、数据预览/查询
          ├─ MaskingService    脱敏规则引擎（识别+变换）
          ├─ JobRunner         异步长任务调度（队列+Worker，可重试/可恢复）
          └─ GovernanceGuard   空间隔离校验、权限校验、审计落库
运行层    解析 Worker（MinerU 自托管） | ETL Worker（清洗/导入）
存储层    Supabase(Postgres+RLS) 结构化表
          对象存储(MinIO/S3) 原始文件、解析产物(Markdown/图片包)
          任务库(Postgres) jobs / job_logs / table_meta / mask_rules / audit_events
```

### 2.2 组件职责

| 组件 | 职责 | 长任务 |
| --- | --- | --- |
| `ParseService` | 接收文件批次，调度解析，归档 Markdown 与图片包，登记产物 | 是 |
| `ETLService` | 按声明式规则做清洗、去重、字段映射，写入目标表 | 是 |
| `SchemaService` | 建表/改字段、生成 DDL、数据预览与分页查询、导出 | 否 |
| `MaskingService` | 按规则识别敏感字段并变换（掩码/哈希/泛化/置空） | 否 |
| `JobRunner` | 队列消费、并发控制、重试、断点恢复、进度上报 | — |
| `GovernanceGuard` | 每次读写前校验空间/团队/角色权限，写审计日志 | 否 |

### 2.3 数据流（端到端）

```text
1) 选文件      用户在数据工作台勾选团队空间内的客户文件（pdf/docx/xlsx/图片…）
2) 解析        ParseService → MinerU 解析 → Markdown + 图片包 → 对象存储归档
3) 抽取为表    解析结果/原始表格 → 识别为「待结构化数据集」
4) 配规则      ETL 配置器：字段映射(源列→目标列) + 清洗规则 + 脱敏规则
5) 试跑        小样本 dry-run，预览清洗后样例与脱敏效果，行级错误回显
6) 落表        ETLService 全量执行 → 写入 Supabase 目标表，更新 table_meta
7) 查询        表管理器分页浏览/条件查询；下游知识工作台与 Agent 直接消费
全程          GovernanceGuard 校验隔离与权限，JobRunner 记录任务日志与审计
```

---

## 3. 文档解析（MinerU）

### 3.1 ParserProvider 抽象

解析能力抽象为统一接口，首版实现自托管 MinerU，预留云端 API 实现，按部署形态切换：

```python
from dataclasses import dataclass

@dataclass
class ParseResult:
    markdown_ref: str          # 对象存储中 Markdown 的引用
    assets_ref: str            # 图片/资源包(zip)的引用
    tables: list[dict]         # 解析出的表格(可直接进入结构化流程)
    meta: dict                 # 页数、耗时、模型版本等

class ParserProvider:
    async def parse(self, file_ref: str, options: dict) -> ParseResult: ...

class MinerULocalProvider(ParserProvider):
    """自托管 MinerU 服务；客户资料不出域。"""
    async def parse(self, file_ref, options):
        # 1) 从对象存储拉取原文件到 Worker 本地临时目录
        # 2) 调用本地 MinerU 推理，产出 markdown + images/
        # 3) 打包 assets，回传对象存储，返回引用
        ...

class MinerUCloudProvider(ParserProvider):
    """预留：调用云端解析 API，用于快速验证/无私有化要求场景。"""
    async def parse(self, file_ref, options): ...
```

> 切换由部署配置 `PARSER_PROVIDER=local|cloud` 决定，业务代码不感知。云端 Provider 仅在客户明确允许数据外发时启用。

### 3.2 解析任务

- **批量**：一次提交多文件，`JobRunner` 按 Worker 并发上限消费，单文件失败不阻断批次。
- **产物**：Markdown（可全屏预览）+ 图片包（可下载，对齐 PRD「输出 Markdown 及图片包下载」）。
- **稳定性治理**（对齐 PRD 7.2.4 稳定性）：大文件分片上传、解析临时文件用后即清、产物流式写对象存储避免内存堆积。

---

## 4. ETL：清洗、字段映射、去重、脱敏

### 4.1 声明式规则模型

清洗与映射用**声明式规则**表达，数据角色在配置器里可视化配置，无需写代码；规则可保存并沉淀为团队资产复用。

```python
@dataclass
class FieldMapping:
    source: str                # 源列名/路径
    target: str                # 目标表字段
    type: str                  # text | int | float | date | bool | json
    required: bool = False

@dataclass
class CleanRule:
    field: str
    op: str                    # trim | lower | regex_replace | drop_if_empty | normalize_date | dedup_key
    args: dict | None = None

@dataclass
class ETLSpec:
    dataset_ref: str           # 来源：解析产物表格 或 上传的 csv/xlsx
    target_table: str          # Supabase 目标表
    mappings: list[FieldMapping]
    cleans: list[CleanRule]
    dedup_keys: list[str]      # 去重主键组合
    mask_rules: list[str]      # 引用 MaskRule.id
    mode: str = "append"       # append | upsert | replace
```

### 4.2 执行流水线

```text
读取数据集 → 字段映射(列对齐+类型转换) → 清洗(逐规则应用) →
去重(按 dedup_keys) → 脱敏(MaskingService) → 校验(必填/类型) →
[dry-run: 返回样例+错误行]  或  [全量: 批量写 Supabase + 记录行数/错误]
```

- **类型转换失败、必填缺失**的行进入「错误样本」，不阻断其余行，日志可下载定位。
- **写入策略**：`append` 追加、`upsert` 按主键更新、`replace` 整表替换；通过 Supabase/PostgREST 批量写入。

### 4.3 脱敏（MaskingService）

满足「敏感数据需要脱敏」的安全硬约束。规则 = 识别 + 变换：

| 变换 | 说明 | 适用 |
| --- | --- | --- |
| `mask` | 部分掩码（保留前后） | 手机号、身份证、卡号 |
| `hash` | 加盐哈希（可保留可比较性） | 需关联但不需明文的标识 |
| `generalize` | 泛化（精确值→区间/类别） | 年龄、金额、地址 |
| `nullify` | 直接置空 | 无分析价值的隐私字段 |

识别方式：**显式指定字段** 为主（数据角色在配置器标注），正则/词典识别为辅。脱敏在落表前执行，**入库即脱敏**，避免明文落地。

---

## 5. 结构化数据后端（Supabase）

### 5.1 表与元数据

- **目标表**：ETL 落入的业务数据表，由 `SchemaService` 按 `ETLSpec.mappings` 生成 DDL 建表。
- **元数据表 `table_meta`**：登记每张目标表的归属空间、团队、来源数据集、字段、行数、最近更新、脱敏标记，供表管理器与运营统计、下游知识工作台发现使用。

### 5.2 查询与权限

- **查询**：表管理器经 PostgREST 做分页浏览与条件过滤；首版支持等值/范围/模糊等基础过滤（对齐 KR10「Supabase 表查询」）。
- **行级安全（RLS）**：每张业务表带 `space_id` / `team_id` 列，启用 Postgres RLS 策略，按当前用户所属空间/团队放行，DB 层兜底隔离，应用层 `GovernanceGuard` 再校验一层。

```sql
-- 示例：团队空间隔离策略
alter table biz_data enable row level security;
create policy team_isolation on biz_data
  using (team_id = current_setting('app.team_id')::uuid);
```

---

## 6. 数据安全治理（对齐 7.3.2 安全 / 7.2.5 权限）

| 治理项 | 实现 |
| --- | --- |
| 空间隔离 | 个人/团队空间 → 对象存储路径前缀 + Supabase `space_id/team_id` 列 + RLS |
| 数据脱敏 | MaskingService 入库前变换，明文不落业务表 |
| 白名单/权限 | 复用平台权限模型；`GovernanceGuard` 每次读写前校验用户对空间/表/任务的访问权 |
| 审计日志 | 解析、导入、查询、脱敏、表结构变更等关键操作写 `audit_events`，含操作人/对象/时间/结果 |
| 稳定性 | 大文件分片上传、临时文件清理、长任务断点恢复（对齐 7.2.4 稳定性治理） |

---

## 7. 异步任务（JobRunner）

### 7.1 任务模型

解析、ETL 导入均为长任务，统一由 `JobRunner` 调度：

```python
from enum import Enum

class JobType(str, Enum):
    PARSE = "parse"; ETL = "etl"

class JobStatus(str, Enum):
    QUEUED = "queued"; RUNNING = "running"; SUCCEEDED = "succeeded"
    FAILED = "failed"; PARTIAL = "partial"; CANCELLED = "cancelled"

@dataclass
class Job:
    job_id: str
    type: JobType
    space_id: str
    team_id: str
    payload: dict              # 文件批次 或 ETLSpec
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0      # 0~1
    stats: dict | None = None  # 行数、成功/失败、耗时
    error_ref: str | None = None  # 错误样本日志引用
```

### 7.2 调度与可靠性

- **队列 + Worker**：任务入队，Worker 池按并发上限消费；解析与 ETL 用不同队列，互不抢占。
- **进度上报**：Worker 周期更新 `progress` 与 `stats`，经 WebSocket 推送到任务日志面板。
- **重试与恢复**：失败任务可重试；批量任务记录已处理位点，支持断点续跑，避免重头再来。
- **可升级**：`JobRunner` 接口稳定，后续需要可视化 DAG / 复杂依赖时可替换为 Airflow/Dagster 等编排引擎，不影响上层服务。

---

## 8. 技术栈与持久化

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 服务 | FastAPI + asyncio | 单进程承载数据平台服务，异步友好 |
| 文档解析 | MinerU（自托管，Provider 抽象） | 客户资料不出域；预留云 API |
| 任务队列 | 轻量队列（Redis/RQ 或 Celery，或 Postgres 队列） | 解析/ETL 长任务调度，首版从轻 |
| 结构化后端 | Supabase（Postgres + PostgREST + RLS + Auth） | 业务表、表查询、行级权限 |
| 对象存储 | MinIO / S3 | 原始文件、解析产物（Markdown/图片包）、错误样本日志 |
| 任务/元数据库 | Postgres | jobs / job_logs / table_meta / mask_rules / audit_events |
| 实时通道 | WebSocket | 解析/导入任务进度与日志流式推送 |

**部署形态**：私有化场景全栈自托管（MinerU + Supabase 自托管 + MinIO），满足客户资料不出域；快速验证场景可用 Supabase 云 + 云解析 API。

---

## 9. 与相邻模块的边界

| 模块 | 边界 | 接口 |
| --- | --- | --- |
| 文件管理（个人/团队空间） | 数据工作台**消费**空间内文件，不负责文件 CRUD | 按 `file_ref` 读取 |
| 知识工作台 | 数据工作台产出结构化表与 Markdown，知识工作台在其上做 RAG/图谱/本体 | `table_meta`、Markdown 产物引用 |
| 权限与成员管理 | 数据工作台**复用**平台权限模型，不自建账号体系 | `GovernanceGuard` 调权限服务 |
| 运营统计后台 | 数据工作台上报任务量、表数、行数等指标 | 写统计事件 |

---

## 10. MVP 范围与实施阶段

### 10.1 MVP 必含（对齐 KR10 + V0.2）

1. MinerU 自托管解析：批量解析 → Markdown + 图片包下载。
2. ETL 声明式规则：字段映射 + 基础清洗 + 去重 + dry-run 预览。
3. 脱敏：mask / hash / nullify 三类变换，入库前生效。
4. Supabase 目标表：建表、字段、基础查询、分页浏览。
5. 空间隔离 + RLS + 审计日志。
6. JobRunner：解析/ETL 异步任务、进度上报、失败重试、错误样本。

### 10.2 MVP 暂不含

- 复杂可视化 DAG 编排（保留 JobRunner 升级口）。
- 自动敏感字段发现（首版以显式标注为主）。
- 跨表 join / 复杂 SQL 构建器（首版基础过滤查询）。
- 增量同步 / 定时拉取（对齐 PRD「定时任务」后续版本）。

### 10.3 并行实施 lanes

```text
Lane A: SchemaService + table_meta + Supabase 建表/查询（无依赖）
Lane B: ParserProvider + MinerU 自托管 Worker（无依赖）
Lane C: JobRunner + 队列 + 进度/重试（无依赖）
After A+C: Lane D: ETLService 规则引擎 + dry-run + 落表
After A:   Lane E: MaskingService 脱敏规则
贯穿:      Lane F: GovernanceGuard 隔离/权限/审计
最后:      Lane G: 数据工作台 UI + WebSocket，E2E 串联
```

---

## 11. 风险与应对

| 风险 | 表现 | 应对 |
| --- | --- | --- |
| MinerU 解析质量不稳 | 复杂版式/扫描件解析差 | 保留人工校对入口；按文档类型调参；必要时切云 Provider 验证 |
| Supabase 私有化能力不足 | 权限/性能/部署不达预期（对应 PRD 假设） | 用 1–2 个真实试点表验证；Schema 层抽象，必要时替换后端 |
| 大文件/批量压垮 Worker | 内存溢出、任务堆积 | 分片上传、流式处理、队列限流、并发上限 |
| 脱敏遗漏 | 敏感字段未标注即入库 | 显式标注 + 正则兜底；审计可回溯；dry-run 强制预览脱敏效果 |
| 隔离配置错误 | 跨团队数据可见 | RLS（DB 层）+ GovernanceGuard（应用层）双重校验；首版验收优先验证 |
| 清洗规则表达力不足 | 复杂转换配不出来 | 规则引擎预留自定义脚本钩子（后续版本） |

---

## 12. 测试策略

| 模块 | 必测 |
| --- | --- |
| ParserProvider | 多格式解析、产物完整性、Provider 切换、失败隔离 |
| ETLService | 字段映射类型转换、清洗逐规则、去重、dry-run 与全量一致性 |
| MaskingService | 各变换正确性、入库前生效、明文不落表 |
| SchemaService | DDL 生成、查询过滤、分页、table_meta 同步 |
| GovernanceGuard | 跨空间访问被拒、RLS 策略生效、审计完整 |
| JobRunner | 并发上限、重试、断点恢复、进度上报、部分成功 |
| E2E | §2.3 全流程：选文件→解析→配规则→dry-run→落表→查询，含隔离与审计校验 |

---

## 13. 结论

数据工作台以「**解析 → 清洗映射脱敏 → Supabase 落表 → 表查询**」为主干，落点在 FastAPI 服务 + 自托管 MinerU + 轻量任务队列 + Supabase。关键工程取舍是：解析用 `ParserProvider` 抽象保私有化、ETL 用声明式规则让数据角色免编程、任务用 `JobRunner` 保长任务可恢复可审计、隔离用 RLS + GovernanceGuard 双层兜底。它为知识工作台与 Agent 提供干净、可控、合规的结构化数据底座，直接支撑 KR10 与 V0.2 现场试点。建议按 §10 的 lanes 先跑通 MVP 闭环，再按需引入自动敏感发现、复杂查询与定时同步。
