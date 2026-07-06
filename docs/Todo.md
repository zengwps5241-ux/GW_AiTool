## 历史对话中部分工具调用缺失调用结果导致一致卡在调用中状态
- 目前已修复，但是修复方式是在前端遍历历史对话，为缺失tool_result的tool_use创建一个tool_result。
- AI的修复结果如下：

  修复方式（frontend/src/pages/ChatWorkspace.tsx）：
  1. 新增 ensureHistoricalToolResults 函数（第 140–158 行）：遍历历史消息，为所有没有对应 tool_result 的 tool_use 追加一条合成的 tool_result（content: ""、is_error: false）。
  2. 在 selectSession 加载历史消息时（第 575 行），先经过 ensureHistoricalToolResults 处理再写入状态。