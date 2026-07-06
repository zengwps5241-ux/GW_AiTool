# 技能与插件分类管理设计

## 背景

当前技能/插件管理页面采用平铺卡片网格展示，技能和插件各自一个 Tab。随着技能/插件数量增加，列表变得冗长难以浏览。本设计引入一套共用的分类体系，将技能管理页和插件管理页改为按分类分组展示，并支持分类的增删改管理。

## 目标

1. 技能和插件共用一套分类体系，分类保存在数据库中
2. 技能/插件列表页按分类分组展示，分类标题显示数量
3. 上传技能/插件时弹窗选择分类并上传 ZIP
4. 初始一个"默认"分类，无法匹配分类的归到默认
5. 分类管理支持新建、重命名、删除（默认分类不可删除）
6. 删除分类时，该分类下所有技能/插件自动移到"默认"分类

## 架构方案：轻量级映射表

保留现有文件系统扫描逻辑，新增数据库表仅存储"分类"和"名称→分类"的映射关系。这是改动最小的方案，无需重构 `scan_skills()` / `scan_plugins()` 核心逻辑。

## 数据库模型

### categories 分类表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, autoincrement | 自增主键 |
| name | String | unique, not null | 分类名称 |
| created_at | DateTime | server_default=now | 创建时间 |

### skill_bindings 技能分类映射

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| skill_name | String | PK | 技能目录名，与文件系统一致 |
| category_id | Integer | FK → categories.id, not null | 所属分类 |

### plugin_bindings 插件分类映射

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| plugin_path | String | PK | 插件相对路径，与文件系统一致 |
| category_id | Integer | FK → categories.id, not null | 所属分类 |

## 迁移策略

在 `migrations.py` 的 `init_db()` 中新增：

1. 创建 `categories` 表（如果不存在）
2. 创建 `skill_bindings` 表（如果不存在）
3. 创建 `plugin_bindings` 表（如果不存在）
4. 插入一条 `name="默认"` 的记录（如果不存在）

**现有数据初始化**：不做迁移期批量扫描。采用**延迟初始化**——当 admin 请求技能/插件列表时，对尚未在绑定表中的技能/插件，自动插入一条指向"默认"分类的绑定记录。

## 后端 API 设计

### 新增路由：`/api/admin/categories`

```
GET    /api/admin/categories        → 200 [{id, name}]
POST   /api/admin/categories        → 201 {id, name}  body: {name}
PATCH  /api/admin/categories/{id}   → 200 {id, name}  body: {name}
DELETE /api/admin/categories/{id}   → 204
```

**删除分类行为**：
- 若目标分类 name="默认"，返回 400 Bad Request
- 将该分类下所有 `skill_bindings` 和 `plugin_bindings` 的 `category_id` 更新为"默认"分类的 id
- 删除该分类记录

### 修改现有路由

**`GET /api/skills`**
- 扫描文件系统后，查 `skill_bindings` + `categories` 获取分类名称
- 返回体增加 `category: string` 字段
- 未绑定的技能自动插入默认绑定（延迟初始化）

**`GET /api/plugins`**
- 同上逻辑，针对插件

**`POST /api/admin/skills/upload`**
- 参数增加：`category_id: int = Form(...)`
- 解压成功后 UPSERT `skill_bindings`（skill_name 为 PK，存在则更新 category_id）

**`POST /api/admin/plugins/upload`**
- 参数增加：`category_id: int = Form(...)`
- 解压成功后 UPSERT `plugin_bindings`

**`DELETE /api/admin/skills/{name}` / `DELETE /api/admin/plugins/{name}`**
- 删除文件后同步删除绑定表中对应记录

## Pydantic Schema 更新

```python
# schemas/skills.py
class SkillOut(BaseModel):
    name: str
    description: str
    category: str | None = None

# schemas/plugins.py
class PluginOut(BaseModel):
    name: str
    version: str
    description: str
    path: str
    category: str | None = None

# schemas/categories.py（新增）
class CategoryOut(BaseModel):
    id: int
    name: str

class CategoryCreate(BaseModel):
    name: str

class CategoryRename(BaseModel):
    name: str
```

## 前端设计

### 页面 Tab 改造

当前两个 Tab（技能管理 / 插件管理）增加第三个 Tab：**分类管理**。

```
技能管理 · N   插件管理 · N   分类管理
```

### 分类展示布局

技能/插件 Tab 下的内容改为按分类分组垂直排列：

```
□ 货源与选品                7
┌──────────────┐  ┌──────────────┐
│ 技能卡片A    │  │ 技能卡片B    │
└──────────────┘  └──────────────┘

〰 市场调研与分析           18
┌──────────────┐  ┌──────────────┐
│ 技能卡片C    │  │ 技能卡片D    │
└──────────────┘  └──────────────┘
```

- **分类标题**：图标 + 分类名 + 数量徽章（圆角灰色小标签）
- **卡片网格**：`grid-template-columns: repeat(auto-fill, minmax(320px, 1fr))`，复用现有卡片样式
- **排序**："默认"分类固定在最前，其余按名称字母序
- **搜索**：关键词过滤卡片，分类数量实时显示匹配数量，无匹配的分类区块隐藏

### 分类管理界面

```
分类管理
─────────────────────────────────
默认                              （不可删除）
数据分析        [重命名]  [删除]
工具集成        [重命名]  [删除]
─────────────────────────────────
[输入新分类名称...]  [新建分类]
```

- 列表项：分类名 + 重命名按钮 + 删除按钮
- 点击"重命名"：该行变为输入框 + 确认/取消
- "默认"分类不显示删除按钮
- 底部固定新建区域

### 上传弹窗

当前上传直接触发 `<input type="file">`，改造为模态弹窗：

```
┌─────────────────────────┐
│ 上传技能                │
│                         │
│ 选择分类                │
│ ┌───────────────────┐   │
│ │ ▼ 默认            │   │
│ └───────────────────┘   │
│                         │
│ 选择文件                │
│ ┌───────────────────┐   │
│ │ 点击或拖拽上传    │   │
│ │     .zip          │   │
│ └───────────────────┘   │
│                         │
│ [取消]      [确认上传]  │
└─────────────────────────┘
```

- 弹窗打开时默认选中"默认"分类
- 文件选择后显示文件名
- 点击确认同时提交分类选择和 ZIP 文件

### TypeScript 类型更新

```typescript
// types/index.ts
export interface Skill {
  name: string;
  description: string;
  category: string;  // 新增
}

export interface Plugin {
  name: string;
  version: string;
  description: string;
  path: string;
  category: string;  // 新增
}

export interface Category {
  id: number;
  name: string;
}
```

## 数据流

### 页面加载

1. SkillsPage 挂载 → 并行请求 `GET /api/skills`、`GET /api/plugins`、`GET /api/admin/categories`
2. 后端首次返回列表时，自动完成延迟初始化（未绑定记录写入默认分类）
3. 前端按 `category` 字段做 `groupBy`，统计数量，排序渲染

### 上传流程

1. 用户点击"上传 ZIP" → 打开上传弹窗
2. 选择分类、选择 ZIP 文件 → 点击确认
3. `POST /api/admin/{skills|plugins}/upload`（FormData: file + category_id）
4. 后端解压成功 → UPSERT 绑定表
5. 前端刷新列表

### 删除分类

1. 用户在"分类管理"tab 点击删除 → 前端二次确认
2. `DELETE /api/admin/categories/{id}`
3. 后端更新绑定表（移到默认）→ 删除分类
4. 前端刷新分类列表和技能/插件列表

## 错误处理

| 场景 | 后端行为 | 前端行为 |
|------|----------|----------|
| 新建分类重名 | 409 Conflict | 提示"分类已存在" |
| 删除"默认"分类 | 400 Bad Request | 按钮直接禁用（双重保护） |
| 上传时分类已被删除 | 422 Unprocessable | 刷新分类列表后重试 |
| 重命名分类名为空 | — | 前端校验拦截 |
| 绑定表与文件系统不一致 | 扫描时自动清理孤立绑定 | — |

## 边界情况

- **覆盖上传**：弹窗始终允许选择分类，若技能/插件已存在则更新其绑定记录
- **文件系统手动删除**：下次扫描时发现绑定记录对应的文件已不存在，自动清理孤立绑定
- **所有技能/插件都被删除**：分类管理界面中各分类显示数量为 0，仍可正常删除空分类
