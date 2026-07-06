import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "@/api/client";
import type {
  LoginWhitelistConfig,
  LoginWhitelistDepartmentSearchItem,
} from "@/types";
import { I } from "@/icons";
import { Btn, Card, Input, Spinner, Tag, useToast } from "@/components/ui";

function formatError(error: unknown): string {
  return error instanceof Error ? error.message : "未知错误";
}

export default function LoginWhitelistPage() {
  const { showToast } = useToast();
  const [config, setConfig] = useState<LoginWhitelistConfig>({
    users: [],
    departments: [],
  });
  const [loading, setLoading] = useState(true);
  const [userName, setUserName] = useState("");
  const [savingUser, setSavingUser] = useState(false);

  const totalCount = useMemo(
    () => config.users.length + config.departments.length,
    [config],
  );

  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      setConfig(await api.loginWhitelist());
    } catch (error) {
      showToast(`加载白名单失败：${formatError(error)}`, "error");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  const addUser = async () => {
    const name = userName.trim();
    if (!name) {
      showToast("请输入用户姓名", "error");
      return;
    }
    setSavingUser(true);
    try {
      const created = await api.createLoginWhitelistUser(name);
      setConfig((prev) => ({ ...prev, users: [...prev.users, created] }));
      setUserName("");
      showToast("用户白名单已添加", "success");
    } catch (error) {
      showToast(`添加用户失败：${formatError(error)}`, "error");
    } finally {
      setSavingUser(false);
    }
  };

  const deleteUser = async (id: number) => {
    try {
      await api.deleteLoginWhitelistUser(id);
      setConfig((prev) => ({
        ...prev,
        users: prev.users.filter((item) => item.id !== id),
      }));
      showToast("用户白名单已删除", "success");
    } catch (error) {
      showToast(`删除用户失败：${formatError(error)}`, "error");
    }
  };

  const addDepartment = async (departmentId: number) => {
    try {
      const created = await api.createLoginWhitelistDepartment(departmentId);
      setConfig((prev) => ({
        ...prev,
        departments: [...prev.departments, created],
      }));
      showToast("部门白名单已添加", "success");
    } catch (error) {
      showToast(`添加部门失败：${formatError(error)}`, "error");
    }
  };

  const deleteDepartment = async (id: number) => {
    try {
      await api.deleteLoginWhitelistDepartment(id);
      setConfig((prev) => ({
        ...prev,
        departments: prev.departments.filter((item) => item.id !== id),
      }));
      showToast("部门白名单已删除", "success");
    } catch (error) {
      showToast(`删除部门失败：${formatError(error)}`, "error");
    }
  };

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "24px 28px" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 18,
        }}
      >
        <div>
          <h1
            style={{
              fontFamily: "var(--serif)",
              fontSize: 24,
              fontWeight: 500,
              marginBottom: 4,
              color: "var(--ink)",
            }}
          >
            用户白名单{" "}
            <span
              style={{
                fontSize: 14,
                color: "var(--ink-3)",
                fontFamily: "var(--sans)",
              }}
            >
              · 共 {totalCount} 项
            </span>
          </h1>
          <div style={{ fontSize: 13, color: "var(--ink-3)" }}>
            配置允许登录本系统的企业微信用户和部门。
          </div>
        </div>
        <Btn
          variant="secondary"
          icon={<I.Refresh size={14} />}
          onClick={() => void loadConfig()}
          disabled={loading}
        >
          刷新
        </Btn>
      </div>

      {loading ? (
        <StateBlock icon={<Spinner />} text="正在加载白名单" />
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 360px), 1fr))",
            gap: 16,
          }}
        >
          <Card style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
            <SectionTitle title="用户姓名" count={config.users.length} />
            <div style={{ display: "flex", gap: 8 }}>
              <Input
                value={userName}
                onChange={(event) => setUserName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void addUser();
                }}
                placeholder="输入企业微信姓名"
              />
              <Btn onClick={() => void addUser()} disabled={savingUser}>添加</Btn>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {config.users.length === 0 ? (
                <EmptyText text="暂无用户姓名白名单" />
              ) : config.users.map((item) => (
                <ListRow
                  key={item.id}
                  title={item.name}
                  onDelete={() => void deleteUser(item.id)}
                />
              ))}
            </div>
          </Card>

          <Card style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
            <SectionTitle title="部门" count={config.departments.length} />
            <DepartmentSearchInput onAdd={(departmentId) => void addDepartment(departmentId)} />
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {config.departments.length === 0 ? (
                <EmptyText text="暂无部门白名单" />
              ) : config.departments.map((item) => (
                <ListRow
                  key={item.id}
                  title={item.path}
                  onDelete={() => void deleteDepartment(item.id)}
                />
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function SectionTitle({ title, count }: { title: string; count: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)" }}>{title}</div>
      <Tag tone="neutral">{count} 项</Tag>
    </div>
  );
}

function EmptyText({ text }: { text: string }) {
  return <div style={{ fontSize: 13, color: "var(--ink-3)", padding: "10px 0" }}>{text}</div>;
}

function DepartmentSearchInput({
  onAdd,
}: {
  onAdd: (departmentId: number) => void;
}) {
  const [keyword, setKeyword] = useState("");
  const [open, setOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<LoginWhitelistDepartmentSearchItem[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  function handleInput(value: string) {
    setKeyword(value);
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!value.trim()) {
      setSuggestions([]);
      setOpen(false);
      return;
    }
    timerRef.current = setTimeout(() => {
      api
        .searchLoginWhitelistDepartments(value.trim())
        .then((list) => {
          setSuggestions(list);
          setOpen(list.length > 0);
        })
        .catch(() => {
          setSuggestions([]);
          setOpen(false);
        });
    }, 200);
  }

  return (
    <div ref={wrapperRef} style={{ position: "relative" }}>
      <Input
        value={keyword}
        onChange={(event) => handleInput(event.target.value)}
        onFocus={() => {
          if (suggestions.length > 0) setOpen(true);
        }}
        placeholder="部门（模糊搜索）"
      />
      {open && suggestions.length > 0 && (
        <div
          style={{
            position: "absolute",
            zIndex: 20,
            top: "calc(100% + 6px)",
            left: 0,
            right: 0,
            background: "var(--surface)",
            border: "1px solid var(--line)",
            borderRadius: 8,
            boxShadow: "var(--shadow-lg)",
            overflow: "hidden",
            maxHeight: 240,
            overflowY: "auto",
          }}
        >
          {suggestions.map((item) => (
            <div
              key={item.department_id}
              onClick={() => {
                onAdd(item.department_id);
                setKeyword(item.path);
                setOpen(false);
              }}
              style={{
                padding: "8px 12px",
                fontSize: 13,
                cursor: "pointer",
                color: "var(--ink)",
                borderBottom: "1px solid var(--line)",
              }}
              onMouseEnter={(event) => {
                (event.currentTarget as HTMLDivElement).style.background = "var(--bg-2)";
              }}
              onMouseLeave={(event) => {
                (event.currentTarget as HTMLDivElement).style.background = "transparent";
              }}
            >
              {item.path}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ListRow({ title, onDelete }: { title: string; onDelete: () => void }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 10,
        border: "1px solid var(--line)",
        borderRadius: 8,
        padding: "9px 10px",
      }}
    >
      <span
        style={{
          minWidth: 0,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          color: "var(--ink-2)",
          fontSize: 13,
        }}
      >
        {title}
      </span>
      <Btn variant="ghost" size="sm" icon={<I.Trash size={14} />} onClick={onDelete} title="删除">
        删除
      </Btn>
    </div>
  );
}

function StateBlock({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <div
      style={{
        minHeight: 260,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        color: "var(--ink-3)",
        fontSize: 13,
      }}
    >
      {icon}
      {text}
    </div>
  );
}
