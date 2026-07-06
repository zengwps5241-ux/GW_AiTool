# 对话模型设置设计

## 目标

在对话输入框中允许用户选择 Claude Agent 使用的模型和思考级别。后端通过 `.env` 支持配置多组模型供应商，每组供应商拥有独立的 `ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_BASE_URL` 和模型数组；前端只展示模型名称，不展示供应商。

## 已确认方案

后端按环境变量前缀自动发现供应商配置：

```env
ANTHROPIC_PROVIDER_DEEPSEEK_AUTH_TOKEN=xxx
ANTHROPIC_PROVIDER_DEEPSEEK_BASE_URL=https://xxx
ANTHROPIC_PROVIDER_DEEPSEEK_MODELS=["deepseek-v4-pro","deepseek-v4-flash"]

ANTHROPIC_PROVIDER_MINIMAX_AUTH_TOKEN=xxx
ANTHROPIC_PROVIDER_MINIMAX_BASE_URL=https://xxx
ANTHROPIC_PROVIDER_MINIMAX_MODELS=["MiniMax-M2.7-highspeed"]
```

新增兼容供应商时只需要添加同样格式的 `.env` 配置，不需要改代码。只有当新供应商不兼容 Anthropic/Claude Agent SDK 网关协议，或需要特殊鉴权、特殊思考参数映射、额外展示元数据时，才需要代码变更。

## 后端设计

- 在配置层解析 `ANTHROPIC_PROVIDER_<KEY>_*` 环境变量，生成供应商列表和模型到供应商的索引。
- 保留旧的单组 `ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_BASE_URL`、`ANTHROPIC_MODEL` 作为兼容配置。
- 新增模型配置接口，返回扁平模型列表和可选思考级别。
- `ChatRequest` 增加 `model` 和 `thinking_level` 字段。
- 运行 Claude Agent 时按所选模型反查供应商，并注入对应 `ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_BASE_URL`，同时传入所选 `model`。
- 思考级别默认 `disabled`；非 `disabled` 时转换为 Claude Agent SDK 的 thinking 配置。

## 前端设计

- 初始加载时请求模型配置。
- 对话输入框底部新增两个紧凑选择器：模型、思考级别。
- 发送消息时把当前选择的模型和思考级别随 `prompt` 一起提交。
- 模型列表只显示模型名，不区分 deepseek、minimax 等供应商。

## 验证策略

- 后端测试覆盖 `.env` 多供应商解析、模型列表接口、聊天请求参数传递、Claude runner 环境注入。
- 前端执行 TypeScript 构建，验证新增字段和组件传参类型正确。
