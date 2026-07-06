# 错误日志方案设计

## 背景

当前系统在 Claude 流式对话、异步文档转换、上传、企微登录等链路中存在多个异常边界。部分异常会返回给前端，但后端没有统一的错误日志落点，排查时难以看到 traceback。第一阶段目标是服务本地调试，不做用户行为采集，也不引入集中式观测平台。

## 目标

- 后端异常能同时输出到控制台和本地日志文件。
- 日志文件自动分片，避免单个文件持续膨胀。
- 日志内容保持极简，只用于错误排障。
- 不采集用户信息，不记录业务内容。
- 先覆盖关键异常边界，避免大范围改造带来噪音。

## 非目标

- 不做 access log 结构化改造。
- 不做 JSON 日志。
- 不做前端错误上报。
- 不做 request id、trace id、用户行为审计。
- 不记录 prompt、回复、文件内容、工具参数、工具返回结果。
- 不记录 username、session_id、agent_id、文件路径等用户或业务上下文。

## 日志内容

第一阶段只记录 `ERROR` 及以上日志，字段使用标准 Python logging 格式：

```text
时间 日志级别 logger 名称 错误消息
traceback
```

允许记录的信息：

- 异常类型。
- 异常消息。
- traceback。
- 代码模块 logger 名称。

不允许记录的信息：

- 用户名、用户 ID。
- 会话 ID、智能体 ID。
- prompt、回复、工具输入、工具输出。
- 文件正文、转换后的 Markdown 内容。
- token、cookie、企业微信 secret、Claude token。
- 工作空间文件路径。

## 日志落点

增加统一日志配置模块，例如：

```text
backend/app/core/logging.py
```

应用启动时在 `backend/app/main.py` 的 lifespan 早期初始化日志。

默认配置：

- 控制台输出：stderr。
- 文件输出：`logs/app.log`。
- 日志级别：`ERROR`。
- 日志目录不存在时自动创建。

环境变量：

```env
LOG_LEVEL=ERROR
LOG_FILE=logs/app.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5
```

## 日志分片

本地文件使用 `logging.handlers.RotatingFileHandler`。

默认策略：

- 单文件最大 `10MB`。
- 最多保留 `5` 个历史文件。
- 文件形态：

```text
logs/app.log
logs/app.log.1
logs/app.log.2
logs/app.log.3
logs/app.log.4
logs/app.log.5
```

达到上限后自动轮转，最旧文件被删除。这个策略足够覆盖本地调试和 Docker 挂载目录排查，避免单文件无限增长。

## 关键异常边界

第一批只在明确异常边界记录 `logger.exception(...)`：

- `backend/app/modules/sessions/streaming.py`
  - `stream_session_chat.runner()` 捕获 Claude 流式执行异常时记录 traceback。
  - 前端仍收到现有错误事件。

- `backend/app/modules/conversions/service.py`
  - `run_conversion_task()` 捕获转换任务异常时记录 traceback。
  - 数据库中的 `error_message` 仍保持用户可读错误。

- `backend/app/integrations/mineru.py`
  - MinerU HTTP 请求异常、非 2xx 响应、返回 zip 非法时记录 traceback 或错误。

- `backend/app/modules/conversions/office_pdf.py`
  - `.doc -> 临时 PDF` 转换失败时记录异常。

- `backend/app/modules/uploads/service.py`
  - 上传单文件失败仍返回批次失败项。
  - 对非预期异常记录 traceback。

- `backend/app/api/routes/auth.py`
  - 企微登录异常已有 `logger.exception`，接入统一日志配置即可。

## 错误处理原则

- 日志面向开发者排障，前端错误面向用户理解，二者分开。
- 捕获异常后，如果业务需要继续返回错误事件或更新任务状态，保持现有行为。
- 不为了日志改变接口返回结构。
- 不在日志中拼接业务上下文，防止后续无意泄露敏感信息。

## 测试策略

- 单元测试日志配置：
  - 初始化后存在控制台 handler 和 rotating file handler。
  - `LOG_FILE`、`LOG_MAX_BYTES`、`LOG_BACKUP_COUNT` 环境变量生效。

- 异常边界测试：
  - 模拟 Claude 流异常，断言调用 `logger.exception`。
  - 模拟转换任务异常，断言任务仍标记 failed，且记录异常。
  - 模拟上传非预期异常，断言批次返回失败项，且记录异常。

- 不要求测试真实文件轮转内容，只验证 handler 配置参数。

## 实施顺序

1. 新增统一日志配置模块。
2. 在应用启动早期初始化日志。
3. 给 Claude SSE、转换任务、MinerU、Office PDF、上传异常边界补 `logger.exception`。
4. 增加配置和异常边界测试。
5. 手动验证本地启动后错误同时出现在控制台和 `logs/app.log`。

## 验收标准

- 人为触发 Claude 流式异常时，控制台和 `logs/app.log` 都能看到 traceback。
- 人为触发转换任务异常时，任务状态仍正确变为 failed，日志文件中有 traceback。
- `logs/app.log` 达到配置大小后能够分片。
- 日志中不出现 prompt、回复、文件正文、工具参数、用户信息。
