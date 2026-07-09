"""顾问方法论 Plugin 的 app 层执行模块（M3.3）。

三个 Plugin 的「绑定/发现」由 ``app/plugins_seed/`` 下的版本化模板目录承载
（供 SDK 加载 + scan_plugins 发现 + init_agent_workdir 拷贝），其实际运行
逻辑位于本包及 ``app/integrations/claude/``（延续 M3.1/M3.2 既定的
「app 层逻辑 + seed 模板」模式，决策 #33）：

- consultant-router（M3.3.1）→ ``router.py``（意图路由 + IntentRoutingLog）
- consultant-search（M3.3.2）→ ``app/integrations/claude/search_tools.py``
- consultant-defense（M3.3.3）→ ``app/integrations/claude/defense.py``
"""
