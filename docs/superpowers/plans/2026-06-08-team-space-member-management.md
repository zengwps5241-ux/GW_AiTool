# Team Space Member Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add owner-only team-space member management and member self-leave support.

**Architecture:** Extend the existing team-space service with explicit member-management methods, expose them through focused FastAPI routes, then wire the existing React member dialog to the new APIs. Keep member list visibility available to all members while gating mutation actions by `space.is_owner`.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, pytest, React, TypeScript, Vite.

---

### Task 1: Backend API and Service

**Files:**
- Modify: `backend/app/modules/team_spaces/service.py`
- Modify: `backend/app/api/routes/team_spaces.py`
- Modify: `backend/app/schemas/team_spaces.py`
- Modify: `frontend/src/api/client.ts`
- Test: `backend/tests/test_team_spaces_api.py`

- [ ] Write failing tests for owner role update, member delete, ownership transfer, member leave, and non-owner forbidden management.
- [ ] Run targeted tests and confirm the new tests fail because routes are missing.
- [ ] Add service methods: `update_member_role`, `remove_member`, `transfer_owner`, `leave_space`.
- [ ] Add FastAPI routes for the four behaviors and return updated `TeamSpaceOut` or `TeamSpaceMemberOut` where useful.
- [ ] Add frontend API client methods matching the new routes.
- [ ] Run targeted backend tests and confirm they pass.

### Task 2: Frontend Member Dialog

**Files:**
- Modify: `frontend/src/pages/TeamSpaceDetailPage.tsx`

- [ ] Render normal members as a read-only list when `space.is_owner` is false.
- [ ] For owners, add per-member role editing, delete, and transfer-owner controls.
- [ ] For non-owners, add a leave-team action.
- [ ] Refresh `space` and member list after each successful mutation.
- [ ] Run `npm run build` and fix any TypeScript errors.

### Task 3: Verification and Commit

**Files:**
- Verify all modified files.

- [ ] Run `pytest backend/tests/test_team_spaces_api.py`.
- [ ] Run `npm run build` in `frontend`.
- [ ] Run `git diff --check`.
- [ ] Commit with a `feat:` or `fix:` message.
