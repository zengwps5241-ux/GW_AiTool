// 登录页:企业微信自建二维码扫码登录
import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { I } from "@/icons";
import { Btn } from "@/components/ui";
import { api } from "@/api/client";

type LoginStatus = "loading" | "waiting" | "scanning" | "error";
const LOGIN_WHITELIST_DENIED_MESSAGE = "当前账号未在登录白名单中，请联系管理员";

function initialLoginError(): string {
  const error = new URLSearchParams(window.location.search).get("error");
  if (error === "login_whitelist_denied") return LOGIN_WHITELIST_DENIED_MESSAGE;
  if (error === "wechat_auth_failed") return "企业微信登录失败，请重试或联系管理员";
  return "";
}

export default function LoginPage({ mode }: { mode: "qrcode" | "sso" }) {
  const initialError = initialLoginError();
  const [qrUrl, setQrUrl] = useState<string>("");
  const [status, setStatus] = useState<LoginStatus>(initialError ? "error" : "loading");
  const [errorMsg, setErrorMsg] = useState(initialError);
  const stateRef = useRef<string>("");
  const abortRef = useRef(false);

  // 构造 OAuth 二维码 URL
  const buildQrUrl = (config: {
    appid: string;
    redirect_uri: string;
    state: string;
    agentid: string;
    scope: string;
  }) => {
    const params = new URLSearchParams();
    params.set("appid", config.appid);
    params.set("redirect_uri", config.redirect_uri);
    params.set("response_type", "code");
    params.set("scope", config.scope);
    params.set("state", config.state);
    params.set("agentid", config.agentid);
    return `https://open.weixin.qq.com/connect/oauth2/authorize?${params.toString()}#wechat_redirect`;
  };

  // 登录流程:拿到 code 后请求后端登录
  const doLogin = async (code: string) => {
    if (abortRef.current) return;
    setStatus("scanning");
    try {
      await api.wechatWorkLoginByCode(code);
      window.location.reload();
    } catch (error) {
      const statusCode = (error as { status?: number }).status;
      setStatus("error");
      setErrorMsg(
        statusCode === 403
          ? LOGIN_WHITELIST_DENIED_MESSAGE
          : "登录失败，请刷新二维码重试",
      );
    }
  };

  // 轮询等待扫码结果
  const pollForCode = async (state: string) => {
    const maxAttempts = 60; // 最多轮询 60 次(5 分钟)
    for (let i = 0; i < maxAttempts; i++) {
      if (abortRef.current) return;
      await new Promise((r) => setTimeout(r, 5000)); // 每 5 秒轮询一次
      if (abortRef.current) return;
      try {
        const result = await api.wechatWorkPollCode(state);
        if (result?.code) {
          await doLogin(result.code);
          return;
        }
      } catch (err: any) {
        const msg = String(err.message || "");
        if (msg.includes("410") || msg.includes("expired")) {
          setStatus("error");
          setErrorMsg("二维码已过期，请刷新");
          return;
        }
        if (msg.includes("404") || msg.includes("not found")) {
          setStatus("error");
          setErrorMsg("无效的请求，请刷新");
          return;
        }
        // 204 或其他网络波动，继续轮询
      }
    }
    setStatus("error");
    setErrorMsg("等待超时，请刷新二维码");
  };

  // 刷新二维码
  const refreshQrCode = async () => {
    if (abortRef.current) return;
    setStatus("loading");
    setErrorMsg("");
    try {
      const config = await api.wechatWorkQrCodeConfig();
      const url = buildQrUrl(config);
      setQrUrl(url);
      stateRef.current = config.state;
      setStatus("waiting");
      pollForCode(config.state);
    } catch {
      setStatus("error");
      setErrorMsg("获取二维码失败，请刷新重试");
    }
  };

  const retryLogin = () => {
    if (mode === "sso") {
      window.location.href = "/api/auth/wechat-work/authorize";
      return;
    }
    void refreshQrCode();
  };

  useEffect(() => {
    abortRef.current = false;
    if (initialError || mode === "sso") return;
    refreshQrCode();
    return () => {
      abortRef.current = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      <div style={{ fontSize: 15, color: "var(--ink-2)" }}>
        请使用企业微信扫码登录
      </div>

      {status === "loading" && (
        <div style={{ fontSize: 13, color: "var(--ink-3)" }}>加载中…</div>
      )}

      {qrUrl && status !== "error" && (
        <div
          style={{
            padding: 16,
            background: "#fff",
            borderRadius: 8,
            border: "1px solid var(--line)",
            lineHeight: 0,
          }}
        >
          <QRCodeSVG value={qrUrl} size={200} level="M" />
        </div>
      )}

      {status === "waiting" && (
        <div style={{ fontSize: 13, color: "var(--ink-3)", display: "flex", alignItems: "center", gap: 6 }}>
          <span
            style={{
              display: "inline-block",
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "var(--accent)",
              animation: "pulse 1.5s infinite",
            }}
          />
          等待扫码…
        </div>
      )}

      {status === "scanning" && (
        <div style={{ fontSize: 13, color: "var(--ink-3)" }}>登录中…</div>
      )}

      {status === "error" && (
        <>
          <div
            style={{
              background: "var(--danger-soft)",
              color: "var(--danger)",
              padding: "10px 14px",
              borderRadius: 8,
              fontSize: 13,
              display: "flex",
              alignItems: "center",
              gap: 8,
              maxWidth: 320,
            }}
          >
            <I.CircleAlert size={14} />
            {errorMsg}
          </div>
          <Btn variant="primary" size="sm" onClick={retryLogin}>
            {mode === "sso" ? "重新登录" : "刷新二维码"}
          </Btn>
        </>
      )}
    </div>
  );
}
