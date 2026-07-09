// 登录页：自建注册登录体系（手机号/用户名+密码）
import { useState } from "react";
import { I } from "@/icons";
import { Btn } from "@/components/ui";
import { api } from "@/api/client";

type LoginTab = "login" | "register";

export default function LoginPage() {
  const [tab, setTab] = useState<LoginTab>("login");

  // 登录表单
  const [loginValue, setLoginValue] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

  // 注册表单
  const [regUsername, setRegUsername] = useState("");
  const [regPhone, setRegPhone] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regDisplayName, setRegDisplayName] = useState("");
  const [regError, setRegError] = useState("");
  const [regSuccess, setRegSuccess] = useState("");
  const [regLoading, setRegLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError("");
    if (!loginValue.trim() || !loginPassword.trim()) {
      setLoginError("请输入用户名/手机号和密码");
      return;
    }
    setLoginLoading(true);
    try {
      await api.login(loginValue.trim(), loginPassword);
      window.location.reload();
    } catch (error: any) {
      const status = error?.status;
      if (status === 401) {
        setLoginError("用户名或密码错误");
      } else if (status === 403) {
        const text = error?.responseText || "";
        if (text.includes("待审批")) {
          setLoginError("账号待审批，请联系管理员");
        } else if (text.includes("禁用")) {
          setLoginError("账号已被禁用，请联系管理员");
        } else {
          setLoginError("无权限登录");
        }
      } else {
        setLoginError("登录失败，请重试");
      }
    } finally {
      setLoginLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setRegError("");
    setRegSuccess("");
    if (!regUsername.trim() && !regPhone.trim()) {
      setRegError("用户名和手机号至少填写一个");
      return;
    }
    if (!regPassword.trim() || regPassword.length < 6) {
      setRegError("密码至少6位");
      return;
    }
    setRegLoading(true);
    try {
      const result = await api.register({
        username: regUsername.trim() || undefined,
        phone: regPhone.trim() || undefined,
        password: regPassword,
        display_name: regDisplayName.trim() || undefined,
      });
      setRegSuccess(result.message || "注册成功，请等待管理员审批");
      setRegUsername("");
      setRegPhone("");
      setRegPassword("");
      setRegDisplayName("");
    } catch (error: any) {
      const status = error?.status;
      if (status === 409) {
        const text = error?.responseText || "";
        if (text.includes("用户名已存在")) {
          setRegError("用户名已存在");
        } else if (text.includes("手机号已注册")) {
          setRegError("手机号已注册");
        } else {
          setRegError("用户名或手机号已存在");
        }
      } else {
        setRegError("注册失败，请重试");
      }
    } finally {
      setRegLoading(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "10px 12px",
    borderRadius: 8,
    border: "1px solid var(--line)",
    background: "var(--surface)",
    color: "var(--ink-1)",
    fontSize: 14,
    outline: "none",
    boxSizing: "border-box",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: 13,
    color: "var(--ink-2)",
    marginBottom: 4,
    display: "block",
  };

  const tabStyle = (active: boolean): React.CSSProperties => ({
    flex: 1,
    padding: "10px 0",
    textAlign: "center",
    fontSize: 14,
    fontWeight: active ? 600 : 400,
    color: active ? "var(--accent)" : "var(--ink-3)",
    borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
    cursor: "pointer",
    background: "none",
    border: "none",
    borderTop: "none",
    borderLeft: "none",
    borderRight: "none",
    outline: "none",
  });

  const errorStyle: React.CSSProperties = {
    background: "var(--danger-soft)",
    color: "var(--danger)",
    padding: "8px 12px",
    borderRadius: 8,
    fontSize: 13,
    display: "flex",
    alignItems: "center",
    gap: 6,
  };

  const successStyle: React.CSSProperties = {
    background: "var(--success-soft, #e8f5e9)",
    color: "var(--success, #2e7d32)",
    padding: "8px 12px",
    borderRadius: 8,
    fontSize: 13,
    display: "flex",
    alignItems: "center",
    gap: 6,
  };

  return (
    <div
      style={{
        minHeight: "100%",
        height: "100%",
        background: "var(--bg)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
        gap: 20,
      }}
    >
      {/* Logo */}
      <div
        style={{
          width: 48,
          height: 48,
          borderRadius: 12,
          background: "var(--surface)",
          border: "1px solid var(--line)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--accent)",
        }}
      >
        <I.Logo size={26} />
      </div>
      <div style={{ fontSize: 18, fontWeight: 600, color: "var(--ink-1)" }}>
        AI 顾问作战台
      </div>

      {/* 登录/注册卡片 */}
      <div
        style={{
          width: 380,
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: 12,
          overflow: "hidden",
        }}
      >
        {/* Tab 切换 */}
        <div style={{ display: "flex", borderBottom: "1px solid var(--line)" }}>
          <button style={tabStyle(tab === "login")} onClick={() => setTab("login")}>
            登录
          </button>
          <button style={tabStyle(tab === "register")} onClick={() => setTab("register")}>
            注册
          </button>
        </div>

        <div style={{ padding: "20px 24px" }}>
          {/* 登录表单 */}
          {tab === "login" && (
            <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <label style={labelStyle}>用户名 / 手机号</label>
                <input
                  style={inputStyle}
                  value={loginValue}
                  onChange={(e) => setLoginValue(e.target.value)}
                  placeholder="请输入用户名或手机号"
                  autoFocus
                />
              </div>
              <div>
                <label style={labelStyle}>密码</label>
                <input
                  style={inputStyle}
                  type="password"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  placeholder="请输入密码"
                />
              </div>
              {loginError && (
                <div style={errorStyle}>
                  <I.CircleAlert size={14} />
                  {loginError}
                </div>
              )}
              <Btn
                variant="primary"
                size="md"
                type="submit"
                disabled={loginLoading}
                style={{ width: "100%", marginTop: 4 }}
              >
                {loginLoading ? "登录中…" : "登录"}
              </Btn>
            </form>
          )}

          {/* 注册表单 */}
          {tab === "register" && (
            <form onSubmit={handleRegister} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <label style={labelStyle}>用户名</label>
                <input
                  style={inputStyle}
                  value={regUsername}
                  onChange={(e) => setRegUsername(e.target.value)}
                  placeholder="请输入用户名"
                />
              </div>
              <div>
                <label style={labelStyle}>手机号</label>
                <input
                  style={inputStyle}
                  value={regPhone}
                  onChange={(e) => setRegPhone(e.target.value)}
                  placeholder="请输入11位手机号"
                  maxLength={11}
                />
              </div>
              <div>
                <label style={labelStyle}>显示名称</label>
                <input
                  style={inputStyle}
                  value={regDisplayName}
                  onChange={(e) => setRegDisplayName(e.target.value)}
                  placeholder="可选，展示名称"
                />
              </div>
              <div>
                <label style={labelStyle}>密码</label>
                <input
                  style={inputStyle}
                  type="password"
                  value={regPassword}
                  onChange={(e) => setRegPassword(e.target.value)}
                  placeholder="至少6位"
                />
              </div>
              {regError && (
                <div style={errorStyle}>
                  <I.CircleAlert size={14} />
                  {regError}
                </div>
              )}
              {regSuccess && (
                <div style={successStyle}>
                  <I.CircleCheck size={14} />
                  {regSuccess}
                </div>
              )}
              <Btn
                variant="primary"
                size="md"
                type="submit"
                disabled={regLoading}
                style={{ width: "100%", marginTop: 4 }}
              >
                {regLoading ? "注册中…" : "注册"}
              </Btn>
              <div style={{ fontSize: 12, color: "var(--ink-3)", textAlign: "center" }}>
                注册后需管理员审批方可使用
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
