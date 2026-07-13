import { useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import type { UserSearchItem } from "@/types";
import { Checkbox, Input } from "@/components/ui";
import { I } from "@/icons";

/**
 * 对象公开/共享控件（M5.5.3，§5.x / §6.3）。
 *
 * 复用于角色卡 / 业务地图节点 / 拜访记录三类编辑弹窗：
 * - 「完全公开」复选：is_public=true → 团队空间公开资产区可见（§6.3）
 * - 「共享给」多选：shared_with ∋ 指定用户 → 对方跨项目可见（§5.x）
 *
 * 受控组件：父级持有 isPublic / sharedWith 状态，变更经 onChange 回传。
 * 用户搜索走防抖 + 序号竞态保护（镜像 TeamSpaceDetailPage 同款范式）。
 *
 * 已知边界：编辑态下既有 shared_with 仅含 user_id（读侧不带姓名），未解析的
 * 既有项以「用户#id」占位展示；新搜索选中的用户带全名。id 列表始终正确。
 */
interface Props {
  isPublic: boolean;
  sharedWith: number[];
  onChange: (next: { is_public: boolean; shared_with: number[] }) => void;
}

export function VisibilityControls({ isPublic, sharedWith, onChange }: Props) {
  // 已选用户信息（id → UserSearchItem），用于展示姓名
  const [known, setKnown] = useState<Map<number, UserSearchItem>>(() => {
    const m = new Map<number, UserSearchItem>();
    for (const id of sharedWith) {
      m.set(id, { user_id: id, username: String(id), display_name: null });
    }
    return m;
  });
  const [keyword, setKeyword] = useState("");
  const [suggestions, setSuggestions] = useState<UserSearchItem[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seqRef = useRef(0);
  const boxRef = useRef<HTMLDivElement>(null);

  // 防抖搜索（200ms + 序号防竞态）
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    const kw = keyword.trim();
    const seq = (seqRef.current += 1);
    if (!kw) {
      setSuggestions([]);
      setOpen(false);
      setSearching(false);
      return;
    }
    setSearching(true);
    timerRef.current = setTimeout(() => {
      api
        .searchUsers(kw)
        .then((items) => {
          if (seq !== seqRef.current) return;
          setSuggestions(items);
          setOpen(true);
        })
        .catch(() => {
          if (seq !== seqRef.current) return;
          setSuggestions([]);
          setOpen(false);
        })
        .finally(() => {
          if (seq === seqRef.current) setSearching(false);
        });
    }, 200);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [keyword]);

  // 点击外部关闭建议下拉
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const addUser = (u: UserSearchItem) => {
    if (!sharedWith.includes(u.user_id)) {
      setKnown((m) => new Map(m).set(u.user_id, u));
      onChange({ is_public: isPublic, shared_with: [...sharedWith, u.user_id] });
    }
    setKeyword("");
    setSuggestions([]);
    setOpen(false);
  };

  const removeUser = (id: number) => {
    onChange({ is_public: isPublic, shared_with: sharedWith.filter((x) => x !== id) });
  };

  return (
    <div
      style={{
        padding: 12,
        background: "var(--bg-2)",
        borderRadius: 8,
        border: "1px solid var(--line)",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <div
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: "var(--ink-2)",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <I.Send size={13} />
        跨项目公开
      </div>

      <Checkbox
        checked={isPublic}
        onChange={(v) => onChange({ is_public: v, shared_with: sharedWith })}
        label="完全公开（团队空间公开资产区可见）"
      />

      <div>
        <div style={{ fontSize: 11, color: "var(--ink-3)", marginBottom: 4 }}>
          共享给指定用户（对方跨项目可见）
        </div>
        <div ref={boxRef} style={{ position: "relative" }}>
          <Input
            placeholder="搜索用户名/姓名添加…"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            icon={searching ? <I.Loader size={13} /> : <I.Search size={13} />}
          />
          {open && suggestions.length > 0 && (
            <div
              style={{
                position: "absolute",
                top: "100%",
                left: 0,
                right: 0,
                marginTop: 4,
                background: "var(--surface)",
                border: "1px solid var(--line)",
                borderRadius: 8,
                boxShadow: "var(--shadow-lg)",
                zIndex: 50,
                maxHeight: 220,
                overflow: "auto",
              }}
            >
              {suggestions.map((u) => (
                <button
                  key={u.user_id}
                  type="button"
                  onClick={() => addUser(u)}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "8px 10px",
                    background: "transparent",
                    border: "none",
                    borderBottom: "1px solid var(--line)",
                    cursor: "pointer",
                    font: "inherit",
                    color: "var(--ink)",
                  }}
                >
                  {u.display_name || u.username}
                  {u.display_name && u.username !== u.display_name && (
                    <span style={{ color: "var(--ink-3)", fontSize: 11, marginLeft: 6 }}>
                      @{u.username}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {sharedWith.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
            {sharedWith.map((id) => {
              const u = known.get(id);
              const label = u && u.display_name ? u.display_name : u ? `@${u.username}` : `用户#${id}`;
              return (
                <span
                  key={id}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                    padding: "3px 8px",
                    background: "var(--accent-soft)",
                    color: "var(--accent)",
                    border: "1px solid var(--accent)",
                    borderRadius: 12,
                    fontSize: 12,
                  }}
                >
                  {label}
                  <button
                    type="button"
                    onClick={() => removeUser(id)}
                    style={{ all: "unset", cursor: "pointer", display: "inline-flex" }}
                    title="移除"
                  >
                    <I.X size={11} />
                  </button>
                </span>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
