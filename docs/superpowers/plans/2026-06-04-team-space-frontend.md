# Team Space Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the team space frontend after the service API stabilizes: space-based navigation, shared team session lists, team cards, and reusable workspace file panels.

**Architecture:** Frontend work consumes the server API from `docs/superpowers/plans/2026-06-04-team-space.md`. It removes the standalone chat workspace entry and presents sessions inside personal/team space entry points while preserving agent-grouped session lists.

**Tech Stack:** React 18, TypeScript, Vite, existing frontend API client and workspace components.

---

## File Structure

- Modify `frontend/src/types/index.ts`: add team space/session/workspace scope types and view names.
- Modify `frontend/src/api/client.ts`: add team space APIs, scoped session APIs, and scoped workspace clients.
- Create `frontend/src/lib/workspaceApi.ts`: personal/team workspace API builders.
- Modify `frontend/src/App.tsx`: remove standalone chat entry routing and add personal/team space view routing.
- Modify `frontend/src/components/Sidebar.tsx`: remove “对话工作台”, add “团队空间”.
- Modify `frontend/src/pages/ChatWorkspace.tsx`: make it reusable for personal/team space chat surfaces.
- Modify `frontend/src/pages/WorkspacePage.tsx`: render the extracted `WorkspaceFileManager` for personal file detail.
- Create `frontend/src/pages/TeamSpacesPage.tsx`: team space card list.
- Create `frontend/src/pages/TeamSpaceDetailPage.tsx`: team space file detail and member controls.
- Create `frontend/src/components/workspace/WorkspaceFileManager.tsx`: shared file manager shell used by personal and team detail/chat side panels.
- Create `frontend/tests/teamSpaceClient.test.ts`: workspace client URL builders.
- Create `frontend/tests/teamSpaceNavigation.test.ts`: route/view mapping.
- Create `frontend/tests/workspaceFileManager.test.ts`: readonly UI predicates.

---

### Task 1: Frontend Types, API Client, and Workspace Client Abstraction

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/lib/workspaceApi.ts`
- Test: `frontend/tests/teamSpaceClient.test.ts`

- [ ] **Step 1: Add failing client tests**

Create `frontend/tests/teamSpaceClient.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { teamWorkspaceApi } from "../src/lib/workspaceApi";

describe("teamWorkspaceApi", () => {
  it("builds team workspace URLs", () => {
    const api = teamWorkspaceApi(12);
    expect(api.previewUrl("README.md")).toBe("/api/team-spaces/12/workspace/preview?path=README.md");
    expect(api.downloadUrl("docs/a.md")).toBe("/api/team-spaces/12/workspace/download?path=docs%2Fa.md");
  });
});
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd frontend && npm test -- teamSpaceClient.test.ts
```

Expected: FAIL because `workspaceApi` does not exist.

- [ ] **Step 3: Add frontend types**

Modify `frontend/src/types/index.ts`:

```typescript
export type WorkspaceKind = "personal" | "team";
export type TeamMemberRole = "reader" | "editor";

export interface TeamSpace {
  id: number;
  name: string;
  description: string | null;
  owner_user_id: number;
  owner_name: string;
  member_count: number;
  locked_by_user_id: number | null;
  locked_by_name: string | null;
  lock_acquired_at: string | null;
  lock_note: string | null;
  member_role: TeamMemberRole;
  can_write: boolean;
  is_owner: boolean;
  readonly_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface TeamSpaceMember {
  id: number;
  user_id: number;
  username: string;
  display_name: string | null;
  role: TeamMemberRole;
  is_owner: boolean;
  added_by_user_id: number;
  created_at: string;
  updated_at: string;
}
```

Extend `Session`:

```typescript
created_by_user_id: number;
created_by_name: string | null;
workspace_kind: WorkspaceKind;
team_space_id: number | null;
team_space_name: string | null;
workspace_member_role: TeamMemberRole | null;
workspace_can_write: boolean;
workspace_readonly_reason: string | null;
```

Extend `ViewName`:

```typescript
| "personalSpace"
| "personalSpaceDetail"
| "teamSpaces"
| "teamSpaceChat"
| "teamSpaceDetail"
```

- [ ] **Step 4: Add API client methods**

Modify `frontend/src/api/client.ts`:

```typescript
teamSpaces(): Promise<TeamSpace[]> {
  return request("/api/team-spaces");
},
createTeamSpace(payload: { name: string; description?: string | null }): Promise<TeamSpace> {
  return request("/api/team-spaces", { method: "POST", body: JSON.stringify(payload) });
},
teamSpace(spaceId: number): Promise<TeamSpace> {
  return request(`/api/team-spaces/${spaceId}`);
},
teamSpaceMembers(spaceId: number): Promise<TeamSpaceMember[]> {
  return request(`/api/team-spaces/${spaceId}/members`);
},
createSession(payload: { agent_id?: number | null; workspace_kind?: WorkspaceKind; team_space_id?: number | null }): Promise<Session> {
  return request("/api/sessions", { method: "POST", body: JSON.stringify(payload) });
},
sessions(params?: { workspace_kind?: WorkspaceKind; team_space_id?: number | null }): Promise<Session[]> {
  const qs = params?.workspace_kind === "team" && params.team_space_id
    ? `?workspace_kind=team&team_space_id=${params.team_space_id}`
    : "";
  return request(`/api/sessions${qs}`);
},
```

- [ ] **Step 5: Add workspace API builder**

Create `frontend/src/lib/workspaceApi.ts`:

```typescript
import { api } from "@/api/client";

const q = (path: string) => encodeURIComponent(path);

export interface WorkspaceApi {
  tree(): Promise<unknown>;
  previewUrl(path: string): string;
  downloadUrl(path: string): string;
}

export function personalWorkspaceApi(): WorkspaceApi {
  return {
    tree: api.workspaceTree,
    previewUrl: api.workspacePreviewUrl,
    downloadUrl: api.workspaceDownloadUrl,
  };
}

export function teamWorkspaceApi(spaceId: number): WorkspaceApi {
  const base = `/api/team-spaces/${spaceId}/workspace`;
  return {
    tree: () => api.request(`${base}/tree`),
    previewUrl: (path: string) => `${base}/preview?path=${q(path)}`,
    downloadUrl: (path: string) => `${base}/download?path=${q(path)}`,
  };
}
```

Export the existing request helper from `frontend/src/api/client.ts`:

```typescript
export { request };
```

- [ ] **Step 6: Run frontend checks**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/lib/workspaceApi.ts frontend/tests/teamSpaceClient.test.ts
git commit -m "feat:添加团队空间前端API类型"
```

---

### Task 2: Frontend Space Navigation and Shared Chat Surfaces

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/pages/ChatWorkspace.tsx`
- Create: `frontend/src/pages/TeamSpacesPage.tsx`
- Create: `frontend/src/pages/TeamSpaceDetailPage.tsx`
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Test: `frontend/tests/teamSpaceNavigation.test.ts`

- [ ] **Step 1: Add frontend behavior tests**

Create `frontend/tests/teamSpaceNavigation.test.ts`:

```typescript
import { describe, expect, it } from "vitest";

type ViewName = "personalSpace" | "personalSpaceDetail" | "teamSpaces" | "teamSpaceChat" | "teamSpaceDetail";

function breadcrumb(view: ViewName, teamName?: string) {
  if (view === "personalSpace") return ["个人空间", "会话列表"];
  if (view === "personalSpaceDetail") return ["个人空间", "文件管理"];
  if (view === "teamSpaces") return ["团队空间", "空间列表"];
  if (view === "teamSpaceChat") return ["团队空间", teamName || "团队会话"];
  return ["团队空间", teamName || "空间详情"];
}

describe("space navigation labels", () => {
  it("uses space entries instead of standalone chat workspace", () => {
    expect(breadcrumb("personalSpace")).toEqual(["个人空间", "会话列表"]);
    expect(breadcrumb("teamSpaceChat", "客户试点资料")).toEqual(["团队空间", "客户试点资料"]);
  });
});
```

- [ ] **Step 2: Run test to verify baseline**

Run:

```bash
cd frontend && npm test -- teamSpaceNavigation.test.ts
```

Expected: PASS for the pure helper test; implementation still needed in app code.

- [ ] **Step 3: Remove standalone chat nav**

Modify `frontend/src/components/Sidebar.tsx`:

```typescript
const items: NavItem[] = [
  { id: "personalSpace", label: "个人空间", icon: I.Folder, group: "主要" },
  { id: "teamSpaces", label: "团队空间", icon: I.Users, group: "主要" },
  { id: "agents", label: "智能体管理", icon: I.Users, group: "管理" },
];
```

- [ ] **Step 4: Route space views**

Modify `frontend/src/App.tsx`:

```typescript
const [selectedTeamSpaceId, setSelectedTeamSpaceId] = useState<number | null>(null);
const [selectedTeamSpaceName, setSelectedTeamSpaceName] = useState<string | null>(null);
```

Set default view after login to `personalSpace`.

Render:

```tsx
{view === "personalSpace" ? (
  <ChatWorkspace mode="personal" me={auth.me} onOpenWorkspaceDetail={() => setView("personalSpaceDetail")} />
) : view === "personalSpaceDetail" ? (
  <WorkspacePage onOpenSessions={() => setView("personalSpace")} />
) : view === "teamSpaces" ? (
  <TeamSpacesPage
    onOpenChat={(space) => {
      setSelectedTeamSpaceId(space.id);
      setSelectedTeamSpaceName(space.name);
      setView("teamSpaceChat");
    }}
    onOpenDetail={(space) => {
      setSelectedTeamSpaceId(space.id);
      setSelectedTeamSpaceName(space.name);
      setView("teamSpaceDetail");
    }}
  />
) : view === "teamSpaceChat" && selectedTeamSpaceId ? (
  <ChatWorkspace
    mode="team"
    teamSpaceId={selectedTeamSpaceId}
    teamSpaceName={selectedTeamSpaceName || "团队空间"}
    me={auth.me}
    onOpenWorkspaceDetail={() => setView("teamSpaceDetail")}
  />
) : view === "teamSpaceDetail" && selectedTeamSpaceId ? (
  <TeamSpaceDetailPage
    spaceId={selectedTeamSpaceId}
    onOpenSessions={() => setView("teamSpaceChat")}
  />
) : view === "agents" ? (
  <AgentsPage me={auth.me} />
) : (
  <ChatWorkspace mode="personal" me={auth.me} onOpenWorkspaceDetail={() => setView("personalSpaceDetail")} />
)}
```

- [ ] **Step 5: Make `ChatWorkspace` mode-aware**

Modify `frontend/src/pages/ChatWorkspace.tsx` props:

```typescript
interface Props {
  mode: "personal" | "team";
  teamSpaceId?: number;
  teamSpaceName?: string;
  me: UserMe;
  onOpenWorkspaceDetail?: () => void;
}
```

Load sessions:

```typescript
const sessionParams = mode === "team" && teamSpaceId
  ? { workspace_kind: "team" as const, team_space_id: teamSpaceId }
  : { workspace_kind: "personal" as const };
const ss = await api.sessions(sessionParams);
```

Create session:

```typescript
const created = await api.createSession({
  agent_id: pickedAgentId,
  workspace_kind: mode,
  team_space_id: mode === "team" ? teamSpaceId : null,
});
```

Right file panel title:

```tsx
<div>
  <span>{mode === "team" ? "团队空间" : "个人空间"}</span>
  {onOpenWorkspaceDetail && (
    <button title="进入空间详情" onClick={onOpenWorkspaceDetail}>
      <I.ExternalLink size={14} />
    </button>
  )}
</div>
```

Keep `groupSessions()` by `agent_name`.

- [ ] **Step 6: Add team spaces page**

Create `frontend/src/pages/TeamSpacesPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { TeamSpace } from "@/types";
import { Btn } from "@/components/ui";
import { I } from "@/icons";

interface Props {
  onOpenChat: (space: TeamSpace) => void;
  onOpenDetail: (space: TeamSpace) => void;
}

export default function TeamSpacesPage({ onOpenChat, onOpenDetail }: Props) {
  const [spaces, setSpaces] = useState<TeamSpace[]>([]);

  useEffect(() => {
    api.teamSpaces().then(setSpaces).catch(() => setSpaces([]));
  }, []);

  return (
    <div style={{ flex: 1, padding: 24, overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>团队空间</h2>
        <Btn variant="primary" icon={<I.Plus size={14} />}>创建团队空间</Btn>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
        {spaces.map((space) => (
          <div key={space.id} style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 14, background: "var(--surface)" }}>
            <button onClick={() => onOpenDetail(space)} style={{ all: "unset", cursor: "pointer", display: "block", width: "100%" }}>
              <div style={{ fontWeight: 700 }}>{space.name}</div>
              <div style={{ color: "var(--ink-3)", fontSize: 12, marginTop: 6 }}>{space.description || "暂无描述"}</div>
            </button>
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <Btn size="sm" icon={<I.MessagesSquare size={14} />} onClick={() => onOpenChat(space)}>对话</Btn>
              <Btn size="sm" variant="secondary" icon={<I.ExternalLink size={14} />} onClick={() => onOpenDetail(space)}>进入</Btn>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Add team detail page shell**

Create `frontend/src/pages/TeamSpaceDetailPage.tsx`:

```tsx
import { Btn } from "@/components/ui";
import { I } from "@/icons";

interface Props {
  spaceId: number;
  onOpenSessions: () => void;
}

export default function TeamSpaceDetailPage({ spaceId, onOpenSessions }: Props) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
      <div style={{ height: 48, display: "flex", alignItems: "center", gap: 12, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>团队空间</h2>
        <Btn size="sm" icon={<I.MessagesSquare size={14} />} onClick={onOpenSessions}>会话列表</Btn>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <WorkspaceFileManager
          title="团队空间"
          api={teamWorkspaceApi(spaceId)}
          onOpenSessions={onOpenSessions}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Sidebar.tsx frontend/src/pages/ChatWorkspace.tsx frontend/src/pages/TeamSpacesPage.tsx frontend/src/pages/TeamSpaceDetailPage.tsx frontend/tests/teamSpaceNavigation.test.ts
git commit -m "feat:调整空间会话入口"
```

---

### Task 3: Shared Workspace File Manager and Readonly UI

**Files:**
- Create: `frontend/src/components/workspace/WorkspaceFileManager.tsx`
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Modify: `frontend/src/pages/TeamSpaceDetailPage.tsx`
- Modify: `frontend/src/pages/ChatWorkspace.tsx`
- Test: `frontend/tests/workspaceFileManager.test.ts`

- [ ] **Step 1: Add readonly predicate test**

Create `frontend/tests/workspaceFileManager.test.ts`:

```typescript
import { describe, expect, it } from "vitest";

function visibleActions(readonly: boolean) {
  return {
    upload: !readonly,
    create: !readonly,
    rename: !readonly,
    remove: !readonly,
    download: true,
    preview: true,
  };
}

describe("workspace file manager readonly actions", () => {
  it("hides write actions when readonly", () => {
    expect(visibleActions(true)).toEqual({
      upload: false,
      create: false,
      rename: false,
      remove: false,
      download: true,
      preview: true,
    });
  });
});
```

- [ ] **Step 2: Extract reusable component**

Create `frontend/src/components/workspace/WorkspaceFileManager.tsx` by moving the tree/preview/task drawer shell from `WorkspacePage.tsx` behind props:

```typescript
interface Props {
  title: string;
  readonly?: boolean;
  api: WorkspaceApi;
  onOpenDetail?: () => void;
  onOpenSessions?: () => void;
}
```

Keep current `WorkspaceTree`, `WorkspacePreview`, upload queue, task drawer, and preview modal behavior. Gate upload/create/rename/move/delete/retry conversion with:

```typescript
if (readonly) {
  showToast("当前空间只读，不能编辑文件", "warning");
  return;
}
```

- [ ] **Step 3: Wire personal detail**

Modify `frontend/src/pages/WorkspacePage.tsx` to render:

```tsx
<WorkspaceFileManager
  title="个人空间"
  api={personalWorkspaceApi()}
  onOpenSessions={onOpenSessions}
/>
```

Add optional prop:

```typescript
interface Props {
  onOpenSessions?: () => void;
}
```

- [ ] **Step 4: Wire team detail and chat side panel**

Modify `TeamSpaceDetailPage.tsx`:

```tsx
<WorkspaceFileManager
  title="团队空间"
  api={teamWorkspaceApi(spaceId)}
  readonly={!space?.can_write}
  onOpenSessions={onOpenSessions}
/>
```

Modify `ChatWorkspace.tsx` right panel to use `WorkspaceFileManager` or a compact variant with:

```tsx
<WorkspaceFileManager
  title={mode === "team" ? "团队空间" : "个人空间"}
  api={mode === "team" ? teamWorkspaceApi(teamSpaceId!) : personalWorkspaceApi()}
  readonly={mode === "team" && currentTeamSpace?.can_write === false}
  onOpenDetail={onOpenWorkspaceDetail}
/>
```

- [ ] **Step 5: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/workspace/WorkspaceFileManager.tsx frontend/src/pages/WorkspacePage.tsx frontend/src/pages/TeamSpaceDetailPage.tsx frontend/src/pages/ChatWorkspace.tsx frontend/tests/workspaceFileManager.test.ts
git commit -m "feat:复用空间文件管理组件"
```

---

---

### Task 4: Frontend Verification and UX Smoke

**Files:**
- Modify only frontend files required by failures found in this task.

- [ ] **Step 1: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
cd frontend && npm test -- --run
```

Expected: PASS.

When this command exits with `Missing script: "test"`, record `frontend npm test unavailable` in the implementation notes and use `npm run build` as the automated verification for this frontend plan.

- [ ] **Step 3: Manual smoke test**

Run frontend:

```bash
cd frontend && npm run dev
```

Verify against a running backend:

1. Sidebar has no “对话工作台”.
2. “个人空间” opens personal sessions by agent group.
3. Personal right file panel title is “个人空间” and the enter icon opens personal file detail.
4. Team space list shows cards with conversation icon.
5. Team conversation opens with shared sessions grouped by agent.
6. Team right file panel title is “团队空间” and the enter icon opens team detail.
7. Team shared session messages display sender names.
8. Readonly team space hides upload/edit/delete actions.

- [ ] **Step 4: Commit final frontend fixes when files changed**

When previous verification steps required code changes, commit those specific files:

```bash
git status --short
git add frontend
git commit -m "fix:完善团队空间前端回归问题"
```

When `git status --short` is empty after verification, skip this commit step.
