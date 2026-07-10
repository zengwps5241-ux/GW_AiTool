// 管理员用户审批页面
import { useEffect, useState, useCallback } from "react";
import { I } from "@/icons";
import { Btn } from "@/components/ui";
import { api } from "@/api/client";

interface PendingUser {
  id: number;
  username: string;
  phone: string | null;
  display_name: string | null;
  status: string;
  registration_source: string;
  created_at: string | null;
}

export default function UserApprovalPage() {
  const [users, setUsers] = useState<PendingUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const fetchPendingUsers = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listPendingUsers();
      setUsers(data as PendingUser[]);
      setError("");
    } catch {
      setError("获取待审批用户列表失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPendingUsers();
  }, [fetchPendingUsers]);

  const handleAction = async (userId: number, action: "approve" | "reject") => {
    setActionLoading(userId);
    try {
      await api.approveUser(userId, action);
      setUsers((prev) => prev.filter((u) => u.id !== userId));
    } catch {
      setError("操作失败，请重试");
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 40, color: "var(--ink-3)", fontSize: 13 }}>
        加载中…
      </div>
    );
  }

  return (
    <div style={{ padding: 24, maxWidth: 800 }}>
      <h2 style={{ fontSize: 18, fontWeight: 600, color: "var(--ink-1)", marginBottom: 16 }}>
        用户审批
      </h2>

      {error && (
        <div
          style={{
            background: "var(--danger-soft)",
            color: "var(--danger)",
            padding: "10px 14px",
            borderRadius: 8,
            fontSize: 13,
            marginBottom: 16,
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <I.CircleAlert size={14} />
          {error}
        </div>
      )}

      {users.length === 0 ? (
        <div
          style={{
            padding: 40,
            textAlign: "center",
            color: "var(--ink-3)",
            fontSize: 14,
            background: "var(--surface)",
            borderRadius: 8,
            border: "1px solid var(--line)",
          }}
        >
          暂无待审批用户
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {users.map((user) => (
            <div
              key={user.id}
              style={{
                background: "var(--surface)",
                border: "1px solid var(--line)",
                borderRadius: 8,
                padding: 16,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div>
                <div style={{ fontSize: 14, fontWeight: 500, color: "var(--ink-1)" }}>
                  {user.display_name || user.username}
                </div>
                <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>
                  用户名：{user.username}
                  {user.phone && <> · 手机：{user.phone}</>}
                  {user.created_at && (
                    <> · 注册时间：{new Date(user.created_at).toLocaleString("zh-CN")}</>
                  )}
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--warn, #ed6c02)",
                    marginTop: 4,
                    display: "inline-block",
                    padding: "2px 8px",
                    borderRadius: 4,
                    background: "var(--warn-soft, #fff3e0)",
                  }}
                >
                  待审批
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <Btn
                  variant="primary"
                  size="sm"
                  disabled={actionLoading === user.id}
                  onClick={() => handleAction(user.id, "approve")}
                >
                  通过
                </Btn>
                <Btn
                  variant="ghost"
                  size="sm"
                  disabled={actionLoading === user.id}
                  onClick={() => handleAction(user.id, "reject")}
                >
                  驳回
                </Btn>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
