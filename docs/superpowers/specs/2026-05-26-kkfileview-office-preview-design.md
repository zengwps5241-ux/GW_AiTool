# kkFileView Office 预览设计

## 背景

当前个人空间的 Office/PDF 文件预览复用了“源文件映射到转换后 Markdown”的链路。点击这类文件时，前端会尝试读取转换后的 Markdown，并在独立个人空间中直接进入可编辑状态。这个行为不符合新的预览目标：

- Office 文档预览交给已部署的 kkFileView。
- PDF 直接使用浏览器原生预览。
- 其他类型文件预览逻辑保持不变。
- 独立个人空间中，Office/PDF 的预览和 Markdown 编辑要分开：点击文件默认预览，右上角点击“编辑”后才进入转换后 Markdown 编辑。
- 聊天页个人空间面板和独立个人空间页的预览规则保持一致。

部署要求是用户浏览器不能直接访问或看到 kkFileView 的内网地址。kkFileView 只能由本项目后端通过内网访问。

## 目标

- 新增 `APP_INTERNAL_BASE_URL` 配置，供 kkFileView 从内网回拉本项目文件。
- 新增 `KKFILEVIEW_BASE_URL` 配置，供本项目后端访问 kkFileView。
- Office 文档默认通过本项目后端同源接口预览，后端反向代理 kkFileView，不向浏览器暴露 kkFileView 地址。
- PDF 默认通过浏览器加载本项目预览接口直接预览原文件。
- Office/PDF 的 Markdown 编辑入口与普通预览入口分离。
- 独立个人空间页和聊天页个人空间预览弹窗复用同一套文件类型判断和预览 URL 生成规则。
- 保留现有文本、Markdown、图片、音频、视频和 unsupported 类型的行为。

## 非目标

- 不新增 Office 在线编辑能力。
- 不让 kkFileView 直接对公网暴露服务。
- 不改变文件上传、转换任务、Markdown 下载和原文件下载能力。
- 不把 Office 保存回原始 doc/docx/ppt/pptx/xls/xlsx 文件。
- 不为 kkFileView 做复杂权限模型；它只通过短期签名文件 URL 读取单个授权文件。

## 配置设计

在 `Settings` 中新增两个配置项：

- `app_internal_base_url: str = ""`
  - 对应环境变量 `APP_INTERNAL_BASE_URL`。
  - 必须是 kkFileView 容器或服务所在网络可访问的本项目后端根地址，例如 `http://backend:8000`。
- `kkfileview_base_url: str = ""`
  - 对应环境变量 `KKFILEVIEW_BASE_URL`。
  - 必须是本项目后端可访问的 kkFileView 根地址，例如 `http://192.168.125.180:8012`。

这两个配置只在 Office 预览链路中强依赖。未配置时，Office 预览接口返回清晰的配置错误；PDF 和其他文件预览不受影响。

`.env.example` 需要补充这两个配置的说明，强调 `KKFILEVIEW_BASE_URL` 不需要也不应暴露给浏览器。

## 文件类型规则

前端和后端统一按后缀区分：

- Office：`doc`、`docx`、`ppt`、`pptx`、`xls`、`xlsx`。
- PDF：`pdf`。
- 可转换文档：Office + PDF。仅在 Markdown 编辑/下载/转换链路中沿用这个概念。
- 其他文本、图片、音频、视频和 unsupported 类型沿用现有分类。

这会改变当前“PDF 属于可转换文档所以预览返回 Markdown”的行为。新规则下，PDF 的普通预览返回 PDF 原文件；只有进入编辑模式时才读取转换后的 Markdown。

## 后端接口设计

### Office 预览代理

新增 `GET /api/workspace/office-preview?path=...`。

职责：

1. 要求当前用户已登录。
2. 校验 `path` 位于当前用户工作区内，目标存在且是 Office 文件。
3. 校验 `APP_INTERNAL_BASE_URL` 和 `KKFILEVIEW_BASE_URL` 已配置。
4. 生成短期签名文件 URL：
   - `${APP_INTERNAL_BASE_URL}/api/workspace/internal-preview-file?...`
   - 参数包含用户、相对路径、过期时间、随机 nonce 或等价防重放字段、HMAC 签名。
5. 将签名文件 URL 做 base64 编码，并拼入 kkFileView `onlinePreview?url=...`。
6. 后端通过内网请求 kkFileView，并把页面响应代理给浏览器。

浏览器始终只访问本项目同源接口，不能看到 `KKFILEVIEW_BASE_URL`。

### kkFileView 资源代理

kkFileView 页面可能引用相对路径的 JS、CSS、图片和后续接口。后端需要提供同源代理能力，例如：

- `/api/workspace/office-preview/proxy/{path:path}`

代理规则：

- 只代理到 `KKFILEVIEW_BASE_URL` 下的路径。
- 拒绝带协议或主机的任意外部 URL，避免开放代理风险。
- 保留必要的 query string。
- 对 HTML 响应中的 kkFileView 内网绝对地址和根相对资源路径做同源代理改写。
- 对 JS/CSS/图片等静态资源按原 Content-Type 流式返回。

如果 kkFileView 实际响应全部使用相对路径，也仍保留代理路径规范，避免后续版本升级时暴露内网地址。

### 签名文件回拉

新增 `GET /api/workspace/internal-preview-file?...`。

职责：

1. 不依赖用户 Cookie，只依赖签名参数。
2. 校验签名、过期时间、用户和路径。
3. 校验目标文件仍位于该用户工作区内，且是签名指定的 Office 文件。
4. 返回原始 Office 文件内容。
5. 设置准确的 `Content-Type`、`Content-Disposition` 和 `Cache-Control: no-store`。

签名使用现有 `APP_SECRET` 作为 HMAC 密钥来源。签名数据至少包含用户名、相对路径、过期时间和 nonce，避免 path 被篡改后仍可复用签名。过期时间建议较短，例如 5 分钟。

### 原文件预览

调整 `GET /api/workspace/preview?path=...` 为“原文件预览”语义：

- 文本、Markdown、JSON、XML 等返回文本内容。
- 图片、音频、视频沿用现有文件响应。
- PDF 返回 PDF 原文件，供浏览器 iframe/embed 原生渲染。
- Office 不在此接口返回转换后的 Markdown，Office 预览由 `office-preview` 负责。
- unsupported 类型仍返回 415。

这个调整能避免 PDF 被旧的 Markdown 映射逻辑截走。

### Markdown 编辑预览

新增 `GET /api/workspace/markdown-preview?path=...`。

职责：

- 专门服务独立个人空间的“编辑转换后 Markdown”模式。
- 普通文本文件可继续返回原文本，便于复用编辑器。
- Office/PDF 源文件按现有 `resolve_preview_path` 映射到转换后的 Markdown。
- 没有 Markdown 映射时返回现有提示：“尚未生成转换后的 Markdown，请等待转换完成或重新转换”。
- 响应头继续携带 `X-Resolved-Preview-Path`，前端用于判断当前编辑的是转换后 Markdown。

`PUT /api/workspace/content` 保存逻辑保持当前语义：普通文本写原文件，Office/PDF 写转换后的 Markdown，不反写源文件。

## 前端设计

### 共享分类与 URL

在 `frontend/src/lib/workspace.ts` 中明确区分：

- `isOfficeName`
- `isPdfName`
- `isConvertibleName`
- `workspacePreviewCategory`

`workspacePreviewCategory` 增加 `office` 和 `pdf` 类别，或者增加等价的模式判断函数。独立个人空间页和聊天页预览弹窗必须复用这些函数。

API client 增加：

- `workspaceOfficePreviewUrl(path)`
- `workspaceMarkdownPreviewUrl(path)`

现有 `workspacePreviewUrl(path)` 保留给原文件预览。

### 独立个人空间页

点击文件默认进入预览模式：

- Office：内容区渲染 iframe，src 为 `workspaceOfficePreviewUrl(path)`。
- PDF：内容区渲染 iframe/embed，src 为 `workspacePreviewUrl(path)`。
- 文本/Markdown：沿用现有文本或 Markdown 渲染/编辑能力。若需要保持当前体验，普通文本文件仍可直接编辑。
- 图片、音视频、unsupported：行为不变。

Office/PDF 工具栏右侧新增“编辑”按钮。点击后：

1. 切换到 Markdown 编辑模式。
2. 使用 `workspaceMarkdownPreviewUrl(path)` 拉取转换后的 Markdown。
3. 有映射时展示现有 Markdown 双栏编辑器。
4. 无映射时展示现有“尚未生成转换后的 Markdown”提示和重试转换入口。
5. 编辑模式下保留“重新加载”“保存”，并增加“返回预览”。

切换文件、返回预览或离开当前文件时，如果已有未保存内容，沿用现有离开确认逻辑。

转换后 Markdown 警告文案保留：“当前查看/编辑的是转换后的 Markdown，不是原始文件。”

### 聊天页个人空间预览弹窗

聊天页预览弹窗没有编辑能力，只需要与独立个人空间页保持相同预览分类：

- Office 走 `workspaceOfficePreviewUrl(path)` iframe。
- PDF 走 `workspacePreviewUrl(path)` iframe/embed。
- 文本、Markdown、图片、音视频、unsupported 逻辑不变。

弹窗里的下载按钮继续下载原文件。

## 错误处理

- `APP_INTERNAL_BASE_URL` 或 `KKFILEVIEW_BASE_URL` 缺失：Office 预览返回 503，前端显示“Office 预览服务未配置”。
- kkFileView 不可达、超时或非 2xx：Office 预览返回 502/504，前端显示“Office 预览服务不可用”，保留下载按钮。
- 签名缺失、过期、被篡改：`internal-preview-file` 返回 401 或 403。
- 文件不存在：返回 404。
- 非 Office 文件访问 `office-preview`：返回 400。
- Office/PDF 点击编辑但尚未生成 Markdown：返回 409，前端显示现有提示并保留重试转换入口。
- 反向代理只允许访问配置的 kkFileView 主机，避免成为任意 URL 代理。

## 测试设计

### 后端测试

- 配置默认值读取正常，环境变量可覆盖 `APP_INTERNAL_BASE_URL` 和 `KKFILEVIEW_BASE_URL`。
- Office 签名 URL 可生成并通过校验。
- 过期签名被拒绝。
- 篡改用户、路径或过期时间后签名被拒绝。
- `internal-preview-file` 只返回签名指定的 Office 文件。
- `office-preview` 对非 Office 文件返回 400。
- `office-preview` 在缺少配置时返回清晰错误。
- `office-preview` 构造 kkFileView `onlinePreview?url=` 时使用 base64 编码后的签名文件 URL。
- `/api/workspace/preview` 对 PDF 返回 PDF 原文件，不再返回 Markdown 映射。
- `/api/workspace/markdown-preview` 对 PDF/Office 仍返回转换后的 Markdown。
- 文本、图片、音频、视频和 unsupported 预览行为保持现有测试覆盖。

### 前端验证

- TypeScript 构建通过。
- 文件分类函数覆盖 Office、PDF、Markdown、文本、图片、音视频、unsupported。
- 独立个人空间页点击 Office 文件默认渲染 Office iframe，不进入 Markdown 编辑器。
- 独立个人空间页点击 PDF 文件默认渲染 PDF iframe。
- Office/PDF 点击“编辑”后调用 Markdown 预览 URL，并进入 Markdown 编辑模式。
- 编辑模式保存仍调用现有保存接口。
- 聊天页个人空间预览弹窗对 Office/PDF 与独立个人空间页使用同一预览规则。

## 风险与取舍

- 反向代理 kkFileView 比 302 跳转复杂，但这是隐藏 kkFileView 内网地址的必要代价。
- HTML/资源路径改写依赖 kkFileView 页面结构。实现时应尽量以通用代理路径处理根相对和相对资源，降低 kkFileView 升级影响。
- 签名文件 URL 虽然不暴露给浏览器，但仍应短期有效并绑定用户与路径，避免日志或代理层泄露后长期可用。
- PDF 不再默认展示转换后的 Markdown，这是本需求的明确行为变化；Markdown 编辑入口保留原转换成果。
- 如果 kkFileView 对某些 Office 文件预览失败，前端只提示服务不可用或预览失败，不回退到 Markdown 预览，避免默认预览和编辑语义再次混在一起。
