// 用户管理 tab（M6.6.2 将实现）
// 左侧组织架构树（复用 OrganizationPage 树逻辑）+ 右侧用户列表表格
// 顶部搜索+筛选+新增；点击组织节点筛选用户
// 操作列：编辑角色/状态/禁用启用/重置密码/审批驳回；待审批用户高亮
export default function UsersTab() {
  return (
    <div
      style={{
        padding: 40,
        color: "var(--ink-3)",
        fontSize: 14,
        textAlign: "center",
      }}
    >
      用户管理（M6.6.2 开发中）
    </div>
  );
}
