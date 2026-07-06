import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
} from "react";
import { api } from "@/api/client";
import WorkspaceFileManager from "@/components/workspace/WorkspaceFileManager";
import { Btn, ConfirmDialog, Input, useToast } from "@/components/ui";
import { I } from "@/icons";
import { teamWorkspaceApi } from "@/lib/workspaceApi";
import type {
  TeamMemberRole,
  TeamSpace,
  TeamSpaceMember,
  TeamSpaceMemberSearchItem,
} from "@/types";

const TEAM_MEMBER_PAGE_SIZE = 10;

interface Props {
  spaceId: number;
  spaceName?: string;
  onOpenSessions: () => void;
  onOpenTeamSpaces: () => void;
}

export default function TeamSpaceDetailPage({
  spaceId,
  spaceName,
  onOpenSessions,
  onOpenTeamSpaces,
}: Props) {
  const { showToast } = useToast();
  const workspaceApi = useMemo(() => teamWorkspaceApi(spaceId), [spaceId]);
  const [space, setSpace] = useState<TeamSpace | null>(null);
  const [membersOpen, setMembersOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.teamSpace(spaceId)
      .then((item) => {
        if (!cancelled) setSpace(item);
      })
      .catch(() => {
        if (!cancelled) setSpace(null);
      });
    return () => {
      cancelled = true;
    };
  }, [spaceId]);

  const title = space?.name || spaceName || "团队空间";
  const readonly = space?.can_write === false;

  return (
    <>
      <WorkspaceFileManager
        title={title}
        api={workspaceApi}
        readonly={readonly}
        readonlyReason={space?.readonly_reason}
        headerActions={
          <Btn
            size="sm"
            variant="secondary"
            icon={<I.Users size={14} />}
            onClick={() => setMembersOpen(true)}
          >
            成员
          </Btn>
        }
        onOpenSessions={onOpenSessions}
      />
      {membersOpen && (
        <TeamMembersDialog
          spaceId={spaceId}
          space={space}
          onClose={() => setMembersOpen(false)}
          onChanged={(nextSpace) => setSpace(nextSpace)}
          onLeft={() => {
            setMembersOpen(false);
            setSpace(null);
            onOpenTeamSpaces();
          }}
          showToast={showToast}
        />
      )}
    </>
  );
}

function TeamMembersDialog({
  spaceId,
  space,
  onClose,
  onChanged,
  onLeft,
  showToast,
}: {
  spaceId: number;
  space: TeamSpace | null;
  onClose: () => void;
  onChanged: (space: TeamSpace) => void;
  onLeft: () => void;
  showToast: ReturnType<typeof useToast>["showToast"];
}) {
  const [members, setMembers] = useState<TeamSpaceMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [memberKeyword, setMemberKeyword] = useState("");
  const [selectedUser, setSelectedUser] = useState<TeamSpaceMemberSearchItem | null>(null);
  const [suggestions, setSuggestions] = useState<TeamSpaceMemberSearchItem[]>([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [searchingUsers, setSearchingUsers] = useState(false);
  const [role, setRole] = useState<TeamMemberRole>("reader");
  const [memberPage, setMemberPage] = useState(1);
  const [confirmAction, setConfirmAction] = useState<{
    type: "remove" | "transfer";
    member: TeamSpaceMember;
  } | null>(null);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchSeqRef = useRef(0);
  const searchBoxRef = useRef<HTMLDivElement | null>(null);

  const canManageMembers = space?.is_owner === true;
  const canLeaveSpace = space !== null && !space.is_owner;
  const totalMemberPages = Math.max(1, Math.ceil(members.length / TEAM_MEMBER_PAGE_SIZE));
  const pagedMembers = useMemo(
    () =>
      members.slice(
        (memberPage - 1) * TEAM_MEMBER_PAGE_SIZE,
        memberPage * TEAM_MEMBER_PAGE_SIZE,
      ),
    [memberPage, members],
  );

  const loadMembers = useCallback(async () => {
    setLoading(true);
    try {
      setMembers(await api.teamSpaceMembers(spaceId));
    } catch (e) {
      showToast((e as Error).message || "加载成员失败", "error");
    } finally {
      setLoading(false);
    }
  }, [showToast, spaceId]);

  useEffect(() => {
    void loadMembers();
  }, [loadMembers]);

  useEffect(() => {
    setMemberPage(1);
  }, [spaceId]);

  useEffect(() => {
    setMemberPage((page) => Math.min(page, totalMemberPages));
  }, [totalMemberPages]);

  useEffect(() => {
    function closeSuggestions(event: MouseEvent) {
      if (searchBoxRef.current && !searchBoxRef.current.contains(event.target as Node)) {
        setSuggestionsOpen(false);
      }
    }
    document.addEventListener("mousedown", closeSuggestions);
    return () => {
      document.removeEventListener("mousedown", closeSuggestions);
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    };
  }, []);

  const handleMemberKeyword = (value: string) => {
    setMemberKeyword(value);
    setSelectedUser(null);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    const keyword = value.trim();
    searchSeqRef.current += 1;
    const seq = searchSeqRef.current;
    if (!keyword) {
      setSuggestions([]);
      setSuggestionsOpen(false);
      setSearchingUsers(false);
      return;
    }
    setSearchingUsers(true);
    searchTimerRef.current = setTimeout(() => {
      api
        .searchTeamSpaceMemberCandidates(spaceId, keyword)
        .then((items) => {
          if (seq !== searchSeqRef.current) return;
          setSuggestions(items);
          setSuggestionsOpen(true);
        })
        .catch(() => {
          if (seq !== searchSeqRef.current) return;
          setSuggestions([]);
          setSuggestionsOpen(false);
        })
        .finally(() => {
          if (seq === searchSeqRef.current) setSearchingUsers(false);
        });
    }, 200);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedUser || selectedUser.is_member || submitting) return;
    setSubmitting(true);
    try {
      await api.addTeamSpaceMember(spaceId, { user_id: selectedUser.user_id, role });
      const [nextSpace] = await Promise.all([
        api.teamSpace(spaceId),
        loadMembers(),
      ]);
      onChanged(nextSpace);
      setMemberKeyword("");
      setSelectedUser(null);
      setSuggestions([]);
      setSuggestionsOpen(false);
      setRole("reader");
      setMemberPage(Math.max(1, Math.ceil((members.length + 1) / TEAM_MEMBER_PAGE_SIZE)));
      showToast("成员已更新", "success");
    } catch (e) {
      showToast((e as Error).message || "添加成员失败", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const refreshSpaceAndMembers = useCallback(async () => {
    const [nextSpace] = await Promise.all([
      api.teamSpace(spaceId),
      loadMembers(),
    ]);
    onChanged(nextSpace);
  }, [loadMembers, onChanged, spaceId]);

  const updateMemberRole = async (member: TeamSpaceMember, nextRole: TeamMemberRole) => {
    if (member.role === nextRole || member.is_owner || submitting) return;
    setSubmitting(true);
    try {
      await api.updateTeamSpaceMember(spaceId, member.id, { role: nextRole });
      await loadMembers();
      showToast("成员权限已更新", "success");
    } catch (e) {
      showToast((e as Error).message || "更新成员权限失败", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const removeMember = async (member: TeamSpaceMember) => {
    if (member.is_owner || submitting) return;
    setSubmitting(true);
    try {
      await api.removeTeamSpaceMember(spaceId, member.id);
      await refreshSpaceAndMembers();
      setConfirmAction(null);
      showToast("成员已删除", "success");
    } catch (e) {
      showToast((e as Error).message || "删除成员失败", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const transferOwner = async (member: TeamSpaceMember) => {
    if (member.is_owner || submitting) return;
    setSubmitting(true);
    try {
      const nextSpace = await api.transferTeamSpaceOwner(spaceId, member.user_id);
      onChanged(nextSpace);
      await loadMembers();
      setConfirmAction(null);
      showToast("所有权已转让", "success");
    } catch (e) {
      showToast((e as Error).message || "转让所有权失败", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const leaveSpace = async () => {
    if (submitting) return;
    if (!confirm("确认离开该团队空间?")) return;
    setSubmitting(true);
    try {
      await api.leaveTeamSpace(spaceId);
      showToast("已离开团队空间", "success");
      onLeft();
    } catch (e) {
      showToast((e as Error).message || "离开团队失败", "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(0,0,0,0.36)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(620px, 100%)",
          height: "min(720px, calc(100vh - 32px))",
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: 8,
          boxShadow: "var(--shadow-lg)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: 52,
            flexShrink: 0,
            padding: "0 16px",
            borderBottom: "1px solid var(--line)",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <I.Users size={16} />
          <h3 style={{ flex: 1, margin: 0, fontSize: 16 }}>成员管理</h3>
          <button
            type="button"
            onClick={onClose}
            title="关闭"
            className="focus-ring"
            style={{
              width: 28,
              height: 28,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              border: "1px solid var(--line)",
              borderRadius: 6,
              background: "transparent",
              color: "var(--ink-3)",
              cursor: "pointer",
            }}
          >
            <I.X size={14} />
          </button>
        </div>

        <div style={{ flex: 1, minHeight: 0, padding: 16, overflow: "auto" }}>
          {canManageMembers && (
            <form
              onSubmit={submit}
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
                marginBottom: 16,
                alignItems: "center",
              }}
            >
              <div
                ref={searchBoxRef}
                style={{ position: "relative", flex: "1 1 220px" }}
              >
                <Input
                  value={memberKeyword}
                  onChange={(e) => handleMemberKeyword(e.target.value)}
                  onFocus={() => {
                    if (suggestions.length > 0) setSuggestionsOpen(true);
                  }}
                  placeholder="按姓名模糊搜索用户"
                />
                {suggestionsOpen && (
                  <div
                    style={{
                      position: "absolute",
                      zIndex: 30,
                      top: "calc(100% + 6px)",
                      left: 0,
                      right: 0,
                      maxHeight: 240,
                      overflowY: "auto",
                      background: "var(--surface)",
                      border: "1px solid var(--line)",
                      borderRadius: 8,
                      boxShadow: "var(--shadow-lg)",
                    }}
                  >
                    {searchingUsers && (
                      <div style={memberSuggestionEmptyStyle}>搜索中...</div>
                    )}
                    {!searchingUsers && suggestions.length === 0 && (
                      <div style={memberSuggestionEmptyStyle}>没有匹配用户</div>
                    )}
                    {!searchingUsers &&
                      suggestions.map((item) => (
                        <button
                          key={item.user_id}
                          type="button"
                          disabled={item.is_member}
                          onClick={() => {
                            if (item.is_member) return;
                            setSelectedUser(item);
                            setMemberKeyword(item.display_name || item.username);
                            setSuggestionsOpen(false);
                          }}
                          style={{
                            width: "100%",
                            display: "grid",
                            gridTemplateColumns: "minmax(0, 1fr) auto",
                            gap: 8,
                            alignItems: "center",
                            padding: "9px 12px",
                            border: 0,
                            borderBottom: "1px solid var(--line)",
                            background: "transparent",
                            color: item.is_member ? "var(--ink-3)" : "var(--ink)",
                            cursor: item.is_member ? "not-allowed" : "pointer",
                            textAlign: "left",
                            font: "inherit",
                          }}
                        >
                          <span style={{ minWidth: 0 }}>
                            <span
                              style={{
                                display: "block",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                                fontSize: 13,
                                fontWeight: 700,
                              }}
                            >
                              {item.display_name || item.username}
                            </span>
                            <span
                              style={{
                                display: "block",
                                marginTop: 2,
                                fontSize: 12,
                                color: "var(--ink-3)",
                              }}
                            >
                              {item.username}
                            </span>
                          </span>
                          {item.is_member && <span style={memberBadgeStyle}>已加入</span>}
                        </button>
                      ))}
                  </div>
                )}
              </div>
              <RoleDropdown value={role} onChange={setRole} />
              <Btn
                type="submit"
                icon={submitting ? <I.Loader size={14} /> : <I.Plus size={14} />}
                disabled={submitting || !selectedUser || selectedUser.is_member}
              >
                添加
              </Btn>
            </form>
          )}

          {!canManageMembers && (
            <div
              style={{
                marginBottom: 12,
                padding: "8px 10px",
                borderRadius: 8,
                background: "var(--bg-2)",
                color: "var(--ink-3)",
                fontSize: 12.5,
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <span style={{ flex: 1 }}>
                {space ? "你可以查看成员列表，成员管理仅限空间所有者。" : "正在加载空间权限..."}
              </span>
              {canLeaveSpace && (
                <Btn
                  size="sm"
                  variant="danger"
                  icon={<I.LogOut size={14} />}
                  onClick={() => void leaveSpace()}
                  disabled={submitting}
                >
                  离开团队
                </Btn>
              )}
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {loading && <div style={{ color: "var(--ink-3)", fontSize: 13 }}>加载中…</div>}
            {!loading && members.length === 0 && (
              <div style={{ color: "var(--ink-3)", fontSize: 13 }}>暂无成员</div>
            )}
            {pagedMembers.map((member) => (
              <div
                key={member.id}
                style={{
                  display: "grid",
                  gridTemplateColumns: canManageMembers
                    ? "minmax(0, 1fr) auto auto auto"
                    : "minmax(0, 1fr) auto auto",
                  gap: 10,
                  alignItems: "center",
                  padding: "10px 12px",
                  border: "1px solid var(--line)",
                  borderRadius: 8,
                  background: "var(--bg)",
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 700,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={member.display_name || member.username}
                  >
                    {member.display_name || member.username}
                  </div>
                  <div style={{ marginTop: 2, fontSize: 12, color: "var(--ink-3)" }}>
                    {member.username} · ID {member.user_id}
                  </div>
                </div>
                {member.is_owner && (
                  <span style={memberBadgeStyle}>所有者</span>
                )}
                <span style={memberBadgeStyle}>
                  {member.role === "editor" ? "可编辑" : "只读"}
                </span>
                {canManageMembers && (
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    {!member.is_owner && (
                      <>
                        <RoleDropdown
                          value={member.role}
                          onChange={(nextRole) => void updateMemberRole(member, nextRole)}
                        />
                        <button
                          type="button"
                          className="focus-ring"
                          title="转让所有权"
                          onClick={() => setConfirmAction({ type: "transfer", member })}
                          disabled={submitting}
                          style={memberIconButtonStyle}
                        >
                          <I.Shield size={14} />
                        </button>
                        <button
                          type="button"
                          className="focus-ring"
                          title="删除成员"
                          onClick={() => setConfirmAction({ type: "remove", member })}
                          disabled={submitting}
                          style={{ ...memberIconButtonStyle, color: "var(--danger)" }}
                        >
                          <I.Trash size={14} />
                        </button>
                      </>
                    )}
                    {member.is_owner && (
                      <span style={{ color: "var(--ink-4)", fontSize: 12 }}>当前所有者</span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
          {members.length > TEAM_MEMBER_PAGE_SIZE && (
            <div
              style={{
                marginTop: 12,
                display: "flex",
                justifyContent: "flex-end",
                alignItems: "center",
                gap: 8,
                color: "var(--ink-3)",
                fontSize: 12.5,
              }}
            >
              <span>
                第 {memberPage} / {totalMemberPages} 页 · 共 {members.length} 人
              </span>
              <button
                type="button"
                className="focus-ring"
                onClick={() => setMemberPage((page) => Math.max(1, page - 1))}
                disabled={memberPage <= 1}
                style={memberPagerButtonStyle}
              >
                上一页
              </button>
              <button
                type="button"
                className="focus-ring"
                onClick={() => setMemberPage((page) => Math.min(totalMemberPages, page + 1))}
                disabled={memberPage >= totalMemberPages}
                style={memberPagerButtonStyle}
              >
                下一页
              </button>
            </div>
          )}
        </div>
        <ConfirmDialog
          open={confirmAction !== null}
          title={confirmAction?.type === "transfer" ? "转让所有权" : "删除成员"}
          message={
            confirmAction
              ? confirmAction.type === "transfer"
                ? `确认将团队空间所有权转让给 "${confirmAction.member.display_name || confirmAction.member.username}"？转让后对方将成为新的空间所有者。`
                : `确认删除成员 "${confirmAction.member.display_name || confirmAction.member.username}"？删除后该成员将无法访问此团队空间。`
              : ""
          }
          confirmText={
            submitting
              ? confirmAction?.type === "transfer"
                ? "转让中"
                : "删除中"
              : confirmAction?.type === "transfer"
              ? "转让"
              : "删除"
          }
          variant={confirmAction?.type === "remove" ? "danger" : "primary"}
          onConfirm={() => {
            if (!confirmAction || submitting) return;
            if (confirmAction.type === "transfer") {
              void transferOwner(confirmAction.member);
              return;
            }
            void removeMember(confirmAction.member);
          }}
          onCancel={() => {
            if (!submitting) setConfirmAction(null);
          }}
        />
      </section>
    </div>
  );
}

function RoleDropdown({
  value,
  onChange,
}: {
  value: TeamMemberRole;
  onChange: (role: TeamMemberRole) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const options: Array<{
    value: TeamMemberRole;
    label: string;
    icon: JSX.Element;
  }> = [
    { value: "reader", label: "只读", icon: <I.Eye size={13} /> },
    { value: "editor", label: "可编辑", icon: <I.Edit size={13} /> },
  ];
  const selected = options.find((option) => option.value === value) || options[0];

  useEffect(() => {
    function closeRoleMenu(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", closeRoleMenu);
    return () => document.removeEventListener("mousedown", closeRoleMenu);
  }, []);

  return (
    <div
      ref={wrapperRef}
      style={{
        position: "relative",
        flex: "0 0 auto",
      }}
    >
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((next) => !next)}
        className="focus-ring"
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          minWidth: 128,
          height: 38,
          padding: "0 10px",
          border: "1px solid var(--line)",
          borderRadius: 8,
          background: "var(--surface)",
          color: "var(--ink)",
          cursor: "pointer",
          font: "inherit",
          fontSize: 13,
          fontWeight: 500,
          whiteSpace: "nowrap",
        }}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          {selected.icon}
          {selected.label}
        </span>
        <I.ChevronDown size={14} />
      </button>
      {open && (
        <div
          role="listbox"
          aria-label="成员权限"
          style={{
            position: "absolute",
            zIndex: 30,
            top: "calc(100% + 6px)",
            left: 0,
            right: 0,
            background: "var(--surface)",
            border: "1px solid var(--line)",
            borderRadius: 8,
            boxShadow: "var(--shadow-lg)",
            overflow: "hidden",
          }}
        >
          {options.map((option) => {
            const active = option.value === value;
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                style={{
                  width: "100%",
                  height: 36,
                  display: "flex",
                  alignItems: "center",
                  gap: 7,
                  padding: "0 10px",
                  border: 0,
                  borderBottom: "1px solid var(--line)",
                  background: active ? "var(--accent-soft)" : "transparent",
                  color: active ? "var(--accent-2)" : "var(--ink)",
                  cursor: "pointer",
                  font: "inherit",
                  fontSize: 13,
                  fontWeight: active ? 700 : 500,
                  textAlign: "left",
                }}
              >
                {option.icon}
                <span style={{ flex: 1 }}>{option.label}</span>
                {active && <I.Check size={13} />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

const memberBadgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  minWidth: 52,
  height: 24,
  padding: "0 8px",
  border: "1px solid var(--line)",
  borderRadius: 999,
  background: "var(--surface)",
  color: "var(--ink-3)",
  fontSize: 12,
} satisfies CSSProperties;

const memberIconButtonStyle = {
  width: 32,
  height: 32,
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  border: "1px solid var(--line)",
  borderRadius: 8,
  background: "var(--surface)",
  color: "var(--ink-3)",
  cursor: "pointer",
  padding: 0,
} satisfies CSSProperties;

const memberPagerButtonStyle = {
  height: 30,
  padding: "0 10px",
  border: "1px solid var(--line)",
  borderRadius: 8,
  background: "var(--surface)",
  color: "var(--ink-2)",
  cursor: "pointer",
  font: "inherit",
  fontSize: 12.5,
} satisfies CSSProperties;

const memberSuggestionEmptyStyle = {
  padding: "10px 12px",
  color: "var(--ink-3)",
  fontSize: 13,
} satisfies CSSProperties;
