# Agent Category Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add category assignment and grouped display for agents, reusing the existing skill/plugin category system.

**Architecture:** Persist `category_id` on `agents`, expose `category_id/category` in agent API responses, and let the React management page load categories for grouping and form selection.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, TypeScript, Vite.

---

### Task 1: Backend Agent Category Persistence

**Files:**
- Modify: `backend/app/models/agent.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/schemas/agents.py`
- Modify: `backend/app/modules/agents/service.py`
- Modify: `backend/app/api/routes/agents.py`
- Test: `backend/tests/test_agents_api.py`

- [ ] Write failing tests for creating an agent with `category_id`, listing `category`, and patching `category_id`.
- [ ] Run targeted pytest and confirm failure.
- [ ] Add `category_id` to model and migration defaults.
- [ ] Thread category through schemas, service, and routes.
- [ ] Run targeted pytest and confirm pass.

### Task 2: Frontend Agent Grouping and Form Field

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/AgentsPage.tsx`

- [ ] Extend `Agent` type and API payloads with `category_id/category`.
- [ ] Load categories on `AgentsPage`.
- [ ] Add category to create/edit form state and submit payload.
- [ ] Group filtered agents by category in the list UI.
- [ ] Run `cd frontend && npm run build`.

### Task 3: Verification and Commit

**Files:**
- Include only task-related changed files.

- [ ] Run backend targeted tests.
- [ ] Run frontend build.
- [ ] Check `git status --short` and avoid unrelated workspace changes.
- [ ] Commit with a Chinese message.
