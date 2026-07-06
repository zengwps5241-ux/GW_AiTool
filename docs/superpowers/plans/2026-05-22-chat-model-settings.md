# Chat Model Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add selectable Claude Agent model and thinking level to the chat input, backed by multi-provider `.env` configuration.

**Architecture:** Backend configuration discovers `ANTHROPIC_PROVIDER_<KEY>_*` groups and exposes a flat model list. Chat requests carry `model` and `thinking_level`; the runner resolves the provider by model name and injects the matching Anthropic environment variables into Claude Agent SDK options.

**Tech Stack:** FastAPI, Pydantic Settings, pytest, React, TypeScript, Vite.

---

### Task 1: Backend Provider Configuration

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_config.py`

- [ ] Write failing tests for provider discovery, default models, and model lookup.
- [ ] Run `cd backend && uv run pytest tests/test_config.py -q`.
- [ ] Implement provider parsing and lookup helpers.
- [ ] Run `cd backend && uv run pytest tests/test_config.py -q`.

### Task 2: Backend Chat API and Runner Wiring

**Files:**
- Modify: `backend/app/schemas/sessions.py`
- Modify: `backend/app/api/routes/sessions.py`
- Modify: `backend/app/modules/sessions/streaming.py`
- Modify: `backend/app/integrations/claude/runner.py`
- Test: `backend/tests/test_chat_api.py`
- Test: `backend/tests/test_claude_runner.py`

- [ ] Write failing tests proving `model` and `thinking_level` flow from API request to `stream_chat`.
- [ ] Write failing tests proving runner injects selected provider env and thinking config.
- [ ] Run targeted backend tests and verify expected failures.
- [ ] Implement schema fields, streaming parameters, runner provider resolution, and thinking mapping.
- [ ] Run targeted backend tests.

### Task 3: Model Settings Endpoint

**Files:**
- Create: `backend/app/schemas/model_settings.py`
- Create: `backend/app/api/routes/model_settings.py`
- Modify: `backend/app/api/router.py`
- Test: `backend/tests/test_model_settings_api.py`

- [ ] Write failing API test for flat model list and thinking levels.
- [ ] Implement route and schemas.
- [ ] Run targeted backend tests.

### Task 4: Frontend Chat Controls

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/ChatWorkspace.tsx`

- [ ] Add client types and API call for model settings.
- [ ] Add state and load model settings in `ChatWorkspace`.
- [ ] Add model and thinking selectors to `ChatInput`.
- [ ] Send selected settings through `streamChat`.
- [ ] Run `cd frontend && npm run build`.

### Task 5: Final Verification and Commit

**Files:**
- Modify: `backend/.env.example`

- [ ] Document multi-provider `.env` examples.
- [ ] Run targeted backend tests.
- [ ] Run frontend build.
- [ ] Inspect `git diff` and stage only task-related changes.
- [ ] Commit with a Chinese message.
