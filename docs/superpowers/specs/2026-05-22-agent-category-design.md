# 智能体分类展示设计

## 目标

智能体管理面板支持按分类展示智能体，并在创建、编辑智能体时允许在基础信息里选择分类。分类复用技能管理中的 `categories` 表和管理接口。

## 后端设计

- `agents` 表新增 `category_id`，外键指向 `categories.id`。
- 数据库初始化/迁移时为已有智能体绑定到“默认”分类。
- `AgentOut` 返回 `category_id` 和 `category`。
- `CreateAgentRequest` 与 `UpdateAgentRequest` 支持 `category_id`。
- 创建智能体未传分类时使用“默认”分类。
- 创建/编辑传入不存在的分类时返回 404。

## 前端设计

- `AgentsPage` 初始加载时同时加载 `api.categories()`。
- 智能体列表按分类分组展示，搜索过滤后仍保留分组。
- 创建/编辑弹窗的基础信息区域增加分类下拉选项。
- 保存时提交 `category_id`。

## 验证

- 后端测试覆盖创建、列表、编辑分类字段。
- 前端执行 TypeScript/Vite 构建，验证类型和组件传参正确。
