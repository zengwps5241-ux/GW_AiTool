# goktech-agents 知识工作台 技术方案

> 版本：v1.0
> 日期：2026-05-31
> 定位：售前/方案级技术方案
> 关联文档：《goktech-agent 产品需求文档（PRD）》（同目录 `goktech-agents-prd.md`）、数据工作台技术方案（同目录 `data-platform-tech-design.md`）
> 覆盖需求：KR2（RAG 知识库和基础评测）、7.1.1「知识工作台」页面、7.2.2「知识工作台能力」、7.3.1 知识能力要求

---

## 1. 概述

知识工作台是 goktech-agent 平台「知识」主线的承载页面，职责是**在数据工作台产出的结构化数据与 Markdown 产物之上，构建 Agent 可理解、可检索、可评测的知识表示层**。它处在平台数据流的中间层：

```text
数据工作台 ──► 知识工作台 ──► Agent
结构化表       RAG 知识库      消费检索结果、
Markdown      知识图谱        图谱查询结果、
文件          本体 schema     本体标签过滤
```

### 1.1 核心职责（对齐 PRD 7.2.2）

| 能力 | PRD 要求 | 首版范围 |
| --- | --- | --- |
| RAG 知识库 | 文档切片、向量化、检索、引用溯源 | 必须支持 |
| RAG 评测面板 | 检索效果检查和样本评测 | 基础评测 |
| 知识图谱工作台 | 实体、关系、标签和图谱查询 | 基础能力 |
| 本体工作台 | 本体 schema、业务标签、GraphRAG 预留 | 基础 schema 管理 |

### 1.2 设计取舍（关键决策）

| 决策点 | 选择 | 理由 |
| --- | --- | --- |
| 向量存储 | **专用向量库**（Milvus / Qdrant） | 独立部署，检索性能与扩展性强于 pgvector；支持混合检索与过滤；私有化场景可自托管 |
| 图存储 | **专用图数据库**（Neo4j） | 实体关系多跳查询、图遍历、路径分析是图谱核心需求，Postgres 表模拟难以支撑后续扩展 |
| 嵌入模型 | **EmbeddingProvider 可配置抽象** | 首版接本地/私有化部署的嵌入模型保资料不出域，预留云 API 切换口，与 MinerU 的自托管决策一致 |
| 切片策略 | **固定策略 + 可调参数** | 首版不给用户暴露复杂策略选择；按文档类型预设切片参数，知识角色可在评测面板对比效果再调整 |
| 知识库组织 | 1 项目 = N 知识库，1 知识库 = 1 组文档 + 1 套切片/检索配置 | 对齐 PRD 中"团队空间→项目"的层级；知识库可自由组合数据工作台产出的 Markdown 与结构化表 |
| GraphRAG | **本体工作台预留 schema 建模，图谱查询首版开箱，GraphRAG 留 V1.0** | 对齐 PRD"首版支持基础 schema 管理，后续版本 GraphRAG 深化" |

---

## 2. 总体架构

### 2.1 架构分层

```text
交互层    知识工作台 Web UI
          ├─ RAG 知识库面板    知识库列表、文档来源、切片预览、检索测试、引用溯源
          ├─ 评测面板          评测样本管理、批量跑测、检索效果对比（准确率/召回/MRR）
          ├─ 图谱工作台        实体/关系可视化、Cypher 查询、标签筛选、Path 浏览
          └─ 本体工作台        Schema 编辑、业务标签体系、实体类型定义、GraphRAG 预留
              │  REST / WebSocket（检索结果、评测进度流式推）

服务层    Knowledge Platform Service（FastAPI）
          ├─ RAGService         切片→向量化→检索→溯源（调用 VectorStore + LLM）
          ├─ GraphService       实体抽取、关系抽取、图写入、Cypher 查询
          ├─ OntologyService    Schema CRUD、业务标签管理、GraphRAG 映射预留
          ├─ EvalService        评测样本管理、批量检索跑测、指标计算与对比
          ├─ ChunkingService    多模态切片（Markdown/表格/代码块分类处理）
          └─ EmbeddingProvider  嵌入模型抽象（本地模型/云 API 可切换）

运行层    切片 Worker（异步） | 向量化 Worker | 实体抽取 Worker（异步长任务）
          JobRunner（复用数据工作台任务框架）

存储层    专用向量库（Milvus/Qdrant）  文档 chunk 向量 + 元数据
          专用图数据库（Neo4j）        实体节点 + 关系边 + 属性
          Postgres（元数据与配置）      kb_meta / chunks / eval_samples / eval_runs / ontology_schema / audit_events
          对象存储（MinIO/S3）         原始文档、切片引用
```

### 2.2 组件职责

| 组件 | 职责 | 长任务 |
| --- | --- | --- |
| `RAGService` | 知识库 CRUD、检索（向量+关键词混合）、引用溯源、检索结果聚合 | 否（检索同步） |
| `ChunkingService` | 按文档类型分策略切片（Markdown 标题层级切、表格行级切、代码块整段切），保留上下文窗口重叠 | 是（入库异步） |
| `EmbeddingProvider` | 文本→向量，抽象接口可切换（本地 BGE/M3E 或云端 API） | 是（批量向量化异步） |
| `VectorStore` | chunk 写入/更新/删除、向量相似度检索、元数据过滤、混合检索 | 否 |
| `GraphService` | 实体/关系抽取（调 LLM），写入 Neo4j，提供 Cypher 查询接口 | 是（抽取异步） |
| `OntologyService` | schema 定义（实体类型/属性/关系类型）、业务标签体系管理、GraphRAG 映射预留 | 否 |
| `EvalService` | 评测样本管理（问题-预期文档对）、批量跑测、准确率/召回/MRR 计算、版本对比 | 否 |

### 2.3 数据流（端到端）

```text
1) 选来源     知识角色选择数据工作台产出的 Markdown 文件或结构化表，创建/加入知识库
2) 切片       ChunkingService 按文档类型分策略切片（Markdown 标题、表格行、代码块），保留重叠上下文
3) 向量化     EmbeddingProvider 批量向量化 → VectorStore 写入 chunk + 元数据
4) 实体抽取   GraphService 调 LLM 抽取实体/关系 → Neo4j 写入节点与边
5) 检索就绪   知识库状态变为 active，Agent 可绑定消费
6) 评测       EvalService 跑评测样本，计算检索指标，对比不同切片/检索策略
全程         与数据工作台共享 JobRunner 调度异步长任务（切片/向量化/抽取/批量评测）
```

---

## 3. RAG 知识库

### 3.1 知识库模型

```python
from dataclasses import dataclass, field
from enum import Enum

class KBStatus(str, Enum):
    BUILDING = "building"; ACTIVE = "active"; UPDATING = "updating"; ARCHIVED = "archived"

@dataclass
class KnowledgeBase:
    kb_id: str
    team_id: str
    space_id: str
    name: str
    description: str = ""
    sources: list[str] = field(default_factory=list)  # Markdown/文件/表引用
    chunk_config: dict = field(default_factory=dict)    # 切片大小、重叠、策略
    embedding_model: str = "bge-large-zh"               # 使用的嵌入模型标识
    status: KBStatus = KBStatus.BUILDING
    doc_count: int = 0; chunk_count: int = 0
    created_at: str = ""; updated_at: str = ""
```

### 3.2 切片引擎（ChunkingService）

按文档类型选策略，不对用户暴露复杂度，知识角色可在评测面板对比效果后调整参数：

| 文档类型 | 策略 | 参数 |
| --- | --- | --- |
| Markdown（数据工作台解析产物） | **标题层级切**：按 H1→H2→H3 层级分块，每块保留标题路径作为上下文前缀 | chunk_size=1024, overlap=128 |
| 表格（数据工作台结构化产物） | **行级切**：按固定行数分块，保留表头行作为每块的列名前缀 | rows_per_chunk=50, header_sticky=true |
| 代码块 | **整段切**：一个代码块 = 一个 chunk，不破坏语法 | — |
| 混合文档 | 先按元素类型分组，再各自套对应策略 | — |

- **上下文窗口重叠**：相邻 chunk 保留 128 token 重叠，避免关键信息落边界。
- **元数据携带**：每个 chunk 记录 `{source_doc, page/section, chunk_index, doc_type, team_id}` 支持元数据过滤检索。
- **异步**：切片与向量化走 JobRunner 长任务，知识库状态 `building → active`。

### 3.3 嵌入模型（EmbeddingProvider 可配置抽象）

```python
from dataclasses import dataclass

@dataclass
class EmbeddingResult:
    vectors: list[list[float]]; dim: int; tokens_used: int

class EmbeddingProvider:
    async def embed(self, texts: list[str]) -> EmbeddingResult: ...
    async def embed_query(self, text: str) -> list[float]: ...

class LocalBGEProvider(EmbeddingProvider):
    """本地部署 BGE-large-zh / M3E，资料不出域；GPU Worker 做批量推理。"""
    ...

class CloudEmbeddingProvider(EmbeddingProvider):
    """预留：调用云端嵌入 API，快速验证场景使用。"""
    ...
```

> 切换由部署配置 `EMBEDDING_PROVIDER=local|cloud` 决定。离线批量用 `embed()`，在线检索用 `embed_query()`。

### 3.4 检索与引用溯源

- **混合检索**：向量相似度（语义）+ BM25 关键词（精确匹配），加权融合排序。
- **元数据过滤**：按 `team_id`、`source_doc`、`doc_type` 缩小检索域。
- **引用溯源**：每个检索结果返回 `{source_doc, section, chunk_text, score}`，Agent 对话中以内联引用卡片展示（对齐 PRD AI UI「引用文件卡片预览」）。
- **检索接口**：`RAGService.search(kb_id, query, top_k=10, filters={})` → `list[ChunkResult]`。

---

## 4. RAG 评测面板

### 4.1 评测样本与跑测

对齐 KR2「检索效果检查」。评测样本 = 问题 + 预期相关文档 + 人工标注等级：

```python
@dataclass
class EvalSample:
    sample_id: str; kb_id: str
    question: str
    expected_docs: list[str]     # 预期 chunk ID 列表
    relevance_levels: dict[str, int]  # chunk_id → 0~3 分级（不相关/部分/相关/高相关）

@dataclass
class EvalRun:
    run_id: str; kb_id: str
    config: dict                  # chunk_size/overlap/embedding_model/top_k
    metrics: dict                 # precision / recall / MRR / NDCG
    created_at: str
```

### 4.2 评测流程

```text
评测样本集 ──► 逐样本检索(top_k) ──► 计算命中与排序指标 ──► EvalRun 结果
                                                 │
                                                 ▼ 对比视图：不同配置(run_id)指标并排
```

- **批量跑测**：提交评测样本集，JobRunner 分布式跑，进度 WebSocket 推送。
- **效果对比**：两次 EvalRun 的 precision/recall/MRR/NDCG 并排展示，帮知识角色选择更优的切片/检索参数。
- **样本管理**：新建/导入/编辑评测样本，按知识库分组，支持标注 relevance_level。

---

## 5. 知识图谱工作台

### 5.1 实体/关系模型

首版图谱 = 实体节点 + 关系边 + 属性 + 标签，存储于 Neo4j：

```text
(:Entity {id, name, type, properties, source_doc, team_id})
  -[:RELATES_TO {type, properties, source_doc}]→
(:Entity ...)
```

| 元素 | 说明 | 例 |
| --- | --- | --- |
| Entity | 业务实体节点 | 客户、设备、工单、合同 |
| 属性 | 实体上的 key-value | 设备型号、安装日期 |
| 关系 | 有向边 + 类型 | `设备 -[:归属]→ 客户` |
| 标签 | 实体的业务分类标签 | `#VIP客户` `#核心设备` |

### 5.2 实体抽取（异步，调 LLM）

```text
Markdown/结构化表 ──► LLM 实体抽取 prompt ──► 输出结构化实体/关系 JSON ──► Neo4j 批量写入
```

- **去重**：同名同类型实体按 name+type 唯一键合并，属性追加。
- **人工校对**：图谱面板提供实体/关系列表视图，知识角色可编辑、合并、删除，对齐 PRD「标签体系管理」。
- **查询**：图谱面板提供可视化 Cypher 查询与结果浏览，支持按实体类型/关系类型/标签筛选。

### 5.3 知识图谱与 RAG 的协同

- **检索增强**：Agent 检索时，RAGService 可选地将查询实体链接到图谱，返回实体关联的一跳邻居实体信息作为附加上下文。
- **引用溯源**：每个实体/关系带 `source_doc` 字段，可回链到原始文档。

---

## 6. 本体工作台

### 6.1 Schema 管理

对齐 PRD「本体 schema、业务标签和 GraphRAG 预留」。本体 = 实体类型定义 + 关系类型定义 + 业务标签体系：

```python
@dataclass
class EntityType:
    type_id: str; name: str; description: str
    properties: dict[str, str]   # 属性名 → 类型(text/int/date/entity_ref)
    labels: list[str]            # 业务标签

@dataclass
class RelationType:
    type_id: str; name: str; description: str
    source_type: str; target_type: str
    properties: dict[str, str]
```

知识角色在本体工作台定义"该项目领域有哪些实体类型、哪些关系类型、哪些业务标签"，实体抽取时以此为 schema 约束，提升抽取质量。

### 6.2 GraphRAG 预留

首版完成 schema 建模与基础图谱查询。V1.0 GraphRAG 深化路径：
- 基于本体 schema 做社区发现与摘要
- 图谱上下文注入 Agent 检索（图谱遍历的邻居上下文 → LLM prompt）
- 图谱 + 向量混合检索

`OntologyService` 预留 `graphrag_mapping` 字段，记录 schema 到图算法的映射配置。

---

## 7. 知识库生命周期

```text
创建 ──► 选择文档来源（Markdown/表）──► 配置切片/嵌入参数
  │
  ▼ building: 切片 Worker → 向量化 Worker → 实体抽取 Worker
  │           JobRunner 调度，进度可观测
  ▼ active:  Agent 可绑定，检索可用
  │
  ├─ updating: 增量添加文档，仅处理新增部分
  │
  └─ archived: 归档，不可检索，保留数据
```

- **更新**：增量添加文档时，仅对新文档做切片/向量化/抽取，已有数据不动。
- **删除**：级联清理 VectorStore chunks + Neo4j 实体/关系 + Postgres 元数据。

---

## 8. 技术栈与持久化

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 服务 | FastAPI + asyncio | 与数据工作台同栈 |
| 向量库 | **Milvus / Qdrant**（专用） | 独立部署，混合检索（向量+标量过滤），批量写入，私有化可自托管。Qdrant 轻量适合首版，Milvus 适合大规模 |
| 图数据库 | **Neo4j**（专用） | 实体/关系存储、Cypher 查询、图遍历；社区版自托管 |
| 嵌入模型 | BGE-large-zh / M3E（本地自托管） | EmbeddingProvider 抽象，可切云端 API |
| 任务调度 | JobRunner（复用数据工作台） | 切片、向量化、实体抽取、批量评测均为异步长任务 |
| 元数据/评测 | Postgres | kb_meta / chunks / eval_samples / eval_runs / ontology_schema / audit_events |
| 对象存储 | MinIO / S3 | 原始文档引用、切片缓存 |
| LLM（实体抽取） | Claude API / 本地模型 | 实体/关系抽取 prompt，结构化 JSON 输出 |

---

## 9. 与相邻模块的边界

| 模块 | 边界 | 接口 |
| --- | --- | --- |
| 数据工作台 | 知识工作台**消费**其 Markdown 产物与结构化表，不负责解析/ETL | 读取 ParseResult.markdown_ref、table_meta |
| Agent 中心 / 多任务对话 | Agent 绑定知识库后调用检索接口 | `RAGService.search(kb_id, query)`、`GraphService.query_entity(entity_id)` |
| 团队空间 / 项目资产库 | 知识库配置、评测样本、本体 schema 可作为项目资产快照发布复用 | 资产导出/导入 JSON |
| 权限与成员管理 | 知识工作台复用平台权限模型 | 知识库/图谱/本体按 team_id 隔离 |

---

## 10. MVP 范围与实施阶段

### 10.1 MVP 必含（对齐 KR2 + V0.1/V0.2）

1. RAG 知识库：知识库 CRUD、选择数据工作台 Markdown 作为来源。
2. ChunkingService：Markdown 标题层级切 + 表格行级切 + 上下文重叠。
3. EmbeddingProvider：本地 BGE/M3E 批量向量化 + 向量检索。
4. 混合检索：向量 + BM25 关键词，元数据过滤，引用溯源。
5. 评测面板：评测样本管理、批量跑测、precision/recall/MRR 指标、跑测对比。
6. 知识图谱基础：实体/关系 LLM 抽取 + Neo4j 写入 + Cypher 基础查询 + 人工校对。
7. 本体工作台基础：EntityType/RelationType schema 定义与编辑。

### 10.2 MVP 暂不含

- GraphRAG（社区摘要、图谱增强 Agent 上下文、图向量混合检索）。
- 自动实体类型推断（首版需知识角色在 ontology 手动定义 schema）。
- 跨知识库联邦检索。
- 知识库增量自动同步（后续定时任务）。
- 复杂可视化图谱探索（首版表格式列表 + 基础节点关系图）。

### 10.3 并行实施 lanes

```text
Lane A: VectorStore + EmbeddingProvider + 本地嵌入模型部署（无依赖）
Lane B: Neo4j 部署 + GraphService 基础写入/查询（无依赖）
Lane C: ChunkingService 多策略切片（无依赖）
After A+C: Lane D: RAGService 知识库 CRUD + 混合检索 + 溯源
After B:   Lane E: LLM 实体/关系抽取流水线 + 图谱去重/人工校对
After D:   Lane F: EvalService 评测面板
同期:      Lane G: OntologyService schema 管理
最后:      Lane H: 知识工作台 UI，E2E 串联
```

---

## 11. 风险与应对

| 风险 | 表现 | 应对 |
| --- | --- | --- |
| 切片策略不适配业务文档 | 检索效果差（对应 PRD 假设） | 评测面板做策略对比；支持调整 chunk_size/overlap 再跑测验证 |
| 嵌入模型效果不稳 | 领域文本召回低 | EmbeddingProvider 可切换，评测面板量化对比不同模型效果 |
| LLM 实体抽取幻觉 | 错误实体/关系污染图谱 | 人工校对入口（实体/关系列表可编辑）；仅从已校验的 Markdown 源抽取 |
| Neo4j 运维成本 | 多一个独立组件部署 | 首版社区版单节点足够；预留 Postgres fallback（表模拟） |
| 向量库与图库的私有化部署 | 多组件运维复杂 | 提供 Docker Compose 一键部署；Qdrant 单二进制轻量、Neo4j 社区版容器 |
| 批量向量化耗时长 | 大知识库构建慢 | JobRunner 并发多 Worker；GPU 加速本地嵌入推理 |

---

## 12. 测试策略

| 模块 | 必测 |
| --- | --- |
| ChunkingService | Markdown 标题层级切边界、表格行级切表头保活、上下文重叠正确 |
| EmbeddingProvider | 本地/云端切换、批量与查询向量一致性、维度正确 |
| RAGService | 混合检索排序、元数据过滤、引用溯源完整性 |
| GraphService | 实体去重合并、关系方向正确、Cypher 查询结果、人工编辑生效 |
| OntologyService | Schema CRUD、类型校验、GraphRAG 映射预留 |
| EvalService | 样本 CRUD、批量跑测结果正确、指标计算、多版本对比 |
| E2E | §2.3 全流程：选来源→切片→向量化→实体抽取→检索→评测→溯源，含知识库更新与归档 |

---

## 13. 结论

知识工作台以「**RAG（切片→向量化→混合检索→溯源）+ 知识图谱（实体抽取→Neo4j→Cypher 查询）+ 本体 schema → 评测闭环**」为主干，落点在 FastAPI 服务 + 专用向量库（Milvus/Qdrant）+ Neo4j + 可配置嵌入抽象（本地 BGE/M3E 为主，预留云 API）。关键工程取舍：嵌入模型与 MinerU 对齐可配置抽象保资料不出域、切片策略对用户隐藏但评测面板给知识角色放对比调试口、图谱 LLM 抽取 + 人工校对保质量、本体 schema 做 GraphRAG 预留。它为 Agent 提供"语义检索 + 结构化图谱查询 + 可评测可迭代"的知识底座，直接支撑 KR2 与 V0.1/V0.2。建议按 §10 的 lanes 先跑通 RAG+评测 MVP 闭环，再叠加图谱与本体，最后接入 GraphRAG 深化。
