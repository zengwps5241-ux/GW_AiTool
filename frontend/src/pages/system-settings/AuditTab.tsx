// 日志管理 tab（M6.6.5 将实现）
// 顶部筛选栏（操作人/操作类型/目标类型/时间范围）+ 下方表格（时间/操作人/操作/目标/摘要）
// 点击行展开 detail（JSONB 变更快照 before→after 格式化显示）；默认最近 7 天
export default function AuditTab() {
  return (
    <div
      style={{
        padding: 40,
        color: "var(--ink-3)",
        fontSize: 14,
        textAlign: "center",
      }}
    >
      日志管理（M6.6.5 开发中）
    </div>
  );
}
