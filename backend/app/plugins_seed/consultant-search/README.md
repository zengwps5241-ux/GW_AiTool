# consultant-search（M3.3.2）

WF07 等顾问工作流使用的 MCP 搜索工具集 Plugin。提供 3 个**进程内 MCP 工具**
（`mcp__consultant_search__*`），实际执行逻辑位于
`backend/app/integrations/claude/search_tools.py`（决策 #33：app 层执行模块 +
版本化插件模板）。

## 三个工具

| 工具 | 功能 | 后端 |
|------|------|------|
| `search_web(query, max_results=5)` | 联网搜索公开信息，结果归档个人空间「公开信息/」 | `WEB_SEARCH_API_URL` + `WEB_SEARCH_API_KEY`（或复用 `ZHIPU_WEB_SEARCH_API_KEY`） |
| `search_company_registry(company_name)` | 查询企业工商信息 | `COMPANY_REGISTRY_API_URL` + `COMPANY_REGISTRY_API_KEY`（企查查/天眼查，§4.3 后续对接，未配置返回提示） |
| `fetch_webpage(url)` | 抓取 URL 转 Markdown 并归档 | httpx 直接抓取（无需额外凭据） |

## 配置（.env）

```bash
# web 搜索（不配则 search_web 返回「未配置」提示，AI 据已有资料作答）
WEB_SEARCH_API_URL=https://your-search-endpoint/search
WEB_SEARCH_API_KEY=sk-xxx        # 或复用 ZHIPU_WEB_SEARCH_API_KEY

# 企业工商信息（不配则 search_company_registry 返回「未对接」提示）
COMPANY_REGISTRY_API_URL=https://qcc/api
COMPANY_REGISTRY_API_KEY=xxx
```

> 真实连通性由运营任务 CC-21（智谱 MCP 搜索集成验证）保证；自动化测试通过
> monkeypatch `_http_*` seam 覆盖工具接线/归档/兜底，不依赖真实网络。
