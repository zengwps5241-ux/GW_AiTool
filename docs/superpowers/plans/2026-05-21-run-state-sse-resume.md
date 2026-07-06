# 运行中会话 SSE 恢复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户离开运行中的会话后，再进入该会话时通过新的 SSE 连接恢复最后一轮智能体输出。

**Architecture:** 后端新增内存版 `RunStateStore`，每个会话只保存最后一轮运行事件，并用递增 `seq` 支持补发。现有 chat SSE 负责创建并写入 run state，新增 running 查询和恢复 stream 接口供前端进入会话时恢复。前端保持现有 `ChatEvent[]` 和 `foldEvents` 渲染模型，只在加载历史后追加运行中最后一轮事件并连接恢复流。

**Tech Stack:** FastAPI `StreamingResponse`、asyncio、pytest/pytest-asyncio、React、TypeScript、Vite。

---

## File Structure

- Create: `backend/app/modules/sessions/run_state.py`
  - 进程内 `RunStateStore` 抽象和默认实例。
  - 负责 start、append、snapshot、wait、finish。
  - 只保存最后一轮事件，控制事件数和文本字符数。

- Modify: `backend/app/modules/sessions/streaming.py`
  - 新一轮 chat 开始时创建 run state。
  - Claude 事件到达时写入 run state，再推送当前 SSE。
  - 新增运行中 snapshot 和恢复 SSE 编排函数。

- Modify: `backend/app/api/routes/sessions.py`
  - 新增 `GET /api/sessions/{session_id}/running`。
  - 新增 `GET /api/sessions/{session_id}/running/stream`。

- Modify: `frontend/src/types/index.ts`
  - 新增 `RunEvent`、`RunningSessionState` 类型。

- Modify: `frontend/src/api/client.ts`
  - 新增 `api.sessionRunning()`。
  - 新增 `streamRunningSession()`。

- Modify: `frontend/src/pages/ChatWorkspace.tsx`
  - 选择会话加载历史后检查运行中状态。
  - 运行中则追加最后一轮事件、设置 streaming，并连接恢复 SSE。
  - 抽取结束后的刷新逻辑，供正常发送和恢复流复用。

- Test: `backend/tests/test_run_state.py`
  - 覆盖 store 的覆盖、seq、snapshot、内存限制和等待唤醒。

- Test: `backend/tests/test_chat_api.py`
  - 覆盖 chat 写入 run state、running 查询、running stream 补发。

---

### Task 1: RunStateStore

**Files:**
- Create: `backend/app/modules/sessions/run_state.py`
- Test: `backend/tests/test_run_state.py`

- [ ] **Step 1: Write failing tests for store lifecycle**

Create `backend/tests/test_run_state.py`:

```python
import asyncio

import pytest

from app.modules.sessions.run_state import InMemoryRunStateStore


def test_start_overwrites_previous_run_and_appends_seq():
    store = InMemoryRunStateStore()

    store.start("sid-1", "run-1")
    first = store.append_event("sid-1", {"type": "assistant_text", "text": "旧"})
    assert first == 1

    store.start("sid-1", "run-2")
    second = store.append_event("sid-1", {"type": "assistant_text", "text": "新"})

    snapshot = store.snapshot("sid-1")
    assert second == 1
    assert snapshot is not None
    assert snapshot["run_id"] == "run-2"
    assert snapshot["status"] == "running"
    assert snapshot["latest_seq"] == 1
    assert snapshot["events"] == [
        {"seq": 1, "event": {"type": "assistant_text", "text": "新"}}
    ]


def test_finish_updates_status_and_error_message():
    store = InMemoryRunStateStore()
    store.start("sid-1", "run-1")

    store.finish("sid-1", "failed", error_message="boom")

    snapshot = store.snapshot("sid-1")
    assert snapshot is not None
    assert snapshot["running"] is False
    assert snapshot["status"] == "failed"
    assert snapshot["error_message"] == "boom"


def test_snapshot_since_filters_events_by_seq():
    store = InMemoryRunStateStore()
    store.start("sid-1", "run-1")
    store.append_event("sid-1", {"type": "assistant_text", "text": "一"})
    store.append_event("sid-1", {"type": "assistant_text", "text": "二"})

    snapshot = store.snapshot("sid-1", after_seq=1)

    assert snapshot is not None
    assert snapshot["events"] == [
        {"seq": 2, "event": {"type": "assistant_text", "text": "二"}}
    ]
    assert snapshot["latest_seq"] == 2


def test_store_limits_text_chars_and_emits_error_event():
    store = InMemoryRunStateStore(max_text_chars_per_run=3)
    store.start("sid-1", "run-1")

    store.append_event("sid-1", {"type": "assistant_text", "text": "abcd"})

    snapshot = store.snapshot("sid-1")
    assert snapshot is not None
    assert snapshot["status"] == "failed"
    assert snapshot["events"] == [
        {
            "seq": 1,
            "event": {
                "type": "error",
                "message": "运行中消息缓存超过限制，请等待本轮完成后重新打开会话",
            },
        }
    ]


@pytest.mark.asyncio
async def test_wait_for_event_wakes_after_append():
    store = InMemoryRunStateStore()
    store.start("sid-1", "run-1")

    waiter = asyncio.create_task(store.wait_for_change("sid-1", after_seq=0, timeout=1))
    await asyncio.sleep(0)
    store.append_event("sid-1", {"type": "assistant_text", "text": "来了"})

    assert await waiter is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend && pytest tests/test_run_state.py -q
```

Expected: FAIL because `app.modules.sessions.run_state` does not exist.

- [ ] **Step 3: Implement `RunStateStore`**

Create `backend/app/modules/sessions/run_state.py`:

```python
"""运行中会话最后一轮消息状态。

当前实现使用进程内内存，后续可替换为 Redis 实现。store 只保留每个
session 的最后一轮 run，避免把完整聊天历史堆到内存里。
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Literal, TypedDict


RunStatus = Literal["running", "completed", "failed", "interrupted"]


class RunEvent(TypedDict):
    seq: int
    event: dict


class RunSnapshot(TypedDict):
    running: bool
    session_id: str
    run_id: str
    status: RunStatus
    events: list[RunEvent]
    latest_seq: int
    error_message: str | None


class _RunState(TypedDict):
    session_id: str
    run_id: str
    status: RunStatus
    events: list[RunEvent]
    next_seq: int
    started_at: str
    updated_at: str
    error_message: str | None
    text_chars: int
    cache_disabled: bool


class InMemoryRunStateStore:
    """仅保存每个会话最后一轮运行状态的内存 store。"""

    def __init__(
        self,
        *,
        max_events_per_run: int = 2000,
        max_text_chars_per_run: int = 300_000,
    ) -> None:
        self._states: dict[str, _RunState] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
        self._max_events = max_events_per_run
        self._max_text_chars = max_text_chars_per_run

    def start(self, session_id: str, run_id: str) -> None:
        now = self._now()
        self._states[session_id] = {
            "session_id": session_id,
            "run_id": run_id,
            "status": "running",
            "events": [],
            "next_seq": 1,
            "started_at": now,
            "updated_at": now,
            "error_message": None,
            "text_chars": 0,
            "cache_disabled": False,
        }
        self._conditions.setdefault(session_id, asyncio.Condition())

    def append_event(self, session_id: str, event: dict) -> int | None:
        state = self._states.get(session_id)
        if state is None or state["cache_disabled"]:
            return None

        if self._would_exceed_limits(state, event):
            return self._disable_cache(session_id, state)

        seq = state["next_seq"]
        state["events"].append({"seq": seq, "event": deepcopy(event)})
        state["next_seq"] += 1
        state["updated_at"] = self._now()
        state["text_chars"] += self._event_text_size(event)
        self._notify(session_id)
        return seq

    def finish(
        self,
        session_id: str,
        status: RunStatus,
        *,
        error_message: str | None = None,
    ) -> None:
        state = self._states.get(session_id)
        if state is None:
            return
        state["status"] = status
        state["error_message"] = error_message
        state["updated_at"] = self._now()
        self._notify(session_id)

    def snapshot(self, session_id: str, *, after_seq: int = 0) -> RunSnapshot | None:
        state = self._states.get(session_id)
        if state is None:
            return None
        latest_seq = state["next_seq"] - 1
        events = [
            deepcopy(item)
            for item in state["events"]
            if item["seq"] > after_seq
        ]
        return {
            "running": state["status"] == "running",
            "session_id": state["session_id"],
            "run_id": state["run_id"],
            "status": state["status"],
            "events": events,
            "latest_seq": latest_seq,
            "error_message": state["error_message"],
        }

    async def wait_for_change(
        self,
        session_id: str,
        *,
        after_seq: int,
        timeout: float = 15.0,
    ) -> bool:
        condition = self._conditions.setdefault(session_id, asyncio.Condition())

        def changed() -> bool:
            snapshot = self.snapshot(session_id)
            if snapshot is None:
                return True
            return snapshot["latest_seq"] > after_seq or not snapshot["running"]

        if changed():
            return True
        async with condition:
            try:
                await asyncio.wait_for(condition.wait_for(changed), timeout=timeout)
                return True
            except TimeoutError:
                return False

    def _disable_cache(self, session_id: str, state: _RunState) -> int:
        message = "运行中消息缓存超过限制，请等待本轮完成后重新打开会话"
        state["events"] = [
            {"seq": 1, "event": {"type": "error", "message": message}},
        ]
        state["next_seq"] = 2
        state["status"] = "failed"
        state["error_message"] = message
        state["cache_disabled"] = True
        state["updated_at"] = self._now()
        self._notify(session_id)
        return 1

    def _would_exceed_limits(self, state: _RunState, event: dict) -> bool:
        return (
            len(state["events"]) >= self._max_events
            or state["text_chars"] + self._event_text_size(event) > self._max_text_chars
        )

    def _event_text_size(self, event: dict) -> int:
        text = event.get("text")
        if isinstance(text, str):
            return len(text)
        message = event.get("message")
        if isinstance(message, str):
            return len(message)
        return 0

    def _notify(self, session_id: str) -> None:
        condition = self._conditions.setdefault(session_id, asyncio.Condition())

        async def _do_notify() -> None:
            async with condition:
                condition.notify_all()

        try:
            asyncio.get_running_loop().create_task(_do_notify())
        except RuntimeError:
            return

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


run_state_store = InMemoryRunStateStore()
```

- [ ] **Step 4: Run store tests**

Run:

```bash
cd backend && pytest tests/test_run_state.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/sessions/run_state.py backend/tests/test_run_state.py
git commit -m "feat: add run state store"
```

---

### Task 2: Integrate RunStateStore Into Chat Streaming

**Files:**
- Modify: `backend/app/modules/sessions/streaming.py`
- Test: `backend/tests/test_chat_api.py`

- [ ] **Step 1: Add failing tests for chat run state writes**

Append to `backend/tests/test_chat_api.py`:

```python
async def test_chat_sse_records_last_run_state(logged_in_client, monkeypatch):
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]

    async def fake_stream_chat(*, prompt, claude_session_id, user_workspace, agent, on_message, stop_event=None):
        await on_message({"type": "assistant_text", "text": "第一段"})
        return ChatRunSummary(
            session_id="new-sid",
            is_error=False,
            stop_reason="end_turn",
            usage=None,
            model_usage=None,
            duration_ms=None,
            duration_api_ms=None,
            total_cost_usd=None,
            interrupted=False,
            error_message=None,
        )

    import app.modules.sessions.streaming as streaming_mod
    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)

    async with c.stream("POST", f"/api/sessions/{sid}/chat", json={"prompt": "你好"}) as r:
        async for _ in r.aiter_bytes():
            pass

    snapshot = streaming_mod.run_state_store.snapshot(sid)
    assert snapshot is not None
    assert snapshot["status"] == "completed"
    assert [item["event"] for item in snapshot["events"]] == [
        {"type": "user_text", "text": "你好"},
        {"type": "assistant_text", "text": "第一段"},
    ]


async def test_chat_sse_records_failed_run_state(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import app.modules.sessions.streaming as streaming_mod

    async def fake_stream_chat(**kwargs):
        raise RuntimeError("claude exploded")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, model, session_id):
            return SimpleNamespace(claude_session_id=None, title="", updated_at=None)

        async def commit(self):
            pass

    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(streaming_mod, "async_session", lambda: FakeSession())
    monkeypatch.setattr(streaming_mod, "user_workspace", lambda username: tmp_path)

    response = await streaming_mod.stream_session_chat(
        SimpleNamespace(id="sid-failed", claude_session_id=None, agent_id=None),
        SimpleNamespace(username="alice"),
        "hello",
    )
    async for _ in response.body_iterator:
        pass

    snapshot = streaming_mod.run_state_store.snapshot("sid-failed")
    assert snapshot is not None
    assert snapshot["status"] == "failed"
    assert snapshot["events"][-1]["event"]["type"] == "error"
```

- [ ] **Step 2: Run targeted tests to verify they fail**

Run:

```bash
cd backend && pytest tests/test_chat_api.py::test_chat_sse_records_last_run_state tests/test_chat_api.py::test_chat_sse_records_failed_run_state -q
```

Expected: FAIL because `streaming_mod.run_state_store` is not integrated.

- [ ] **Step 3: Update streaming integration**

Modify `backend/app/modules/sessions/streaming.py`:

```python
import uuid
```

Add import:

```python
from app.modules.sessions.run_state import run_state_store
```

Inside `stream_session_chat`, after `session_id = cs.id`:

```python
    run_id = str(uuid.uuid4())
    run_state_store.start(session_id, run_id)
    run_state_store.append_event(session_id, {"type": "user_text", "text": prompt})
```

Update `on_message`:

```python
    async def on_message(evt: dict) -> None:
        if evt.get("type") == "tool_use":
            tool_uses.append(evt)
        elif evt.get("type") == "tool_result":
            tool_results.append(evt)
        run_state_store.append_event(session_id, evt)
        await queue.put(evt)
```

After `await finalize_usage(summary)` in `runner()`:

```python
            status_value = "interrupted" if summary.interrupted else "failed" if summary.is_error else "completed"
            run_state_store.finish(
                session_id,
                status_value,
                error_message=summary.error_message,
            )
```

In the exception block, after `await queue.put({"type": "error", "message": str(exc)})`:

```python
            run_state_store.append_event(session_id, {"type": "error", "message": str(exc)})
            run_state_store.finish(session_id, "failed", error_message=str(exc))
```

Keep the current SSE behavior unchanged: do not emit the initial `user_text` to the active POST stream because the frontend already appended it locally.

- [ ] **Step 4: Run targeted tests**

Run:

```bash
cd backend && pytest tests/test_chat_api.py::test_chat_sse_records_last_run_state tests/test_chat_api.py::test_chat_sse_records_failed_run_state -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/sessions/streaming.py backend/tests/test_chat_api.py
git commit -m "feat: record chat run state"
```

---

### Task 3: Backend Running Query And Recovery Stream

**Files:**
- Modify: `backend/app/modules/sessions/streaming.py`
- Modify: `backend/app/api/routes/sessions.py`
- Test: `backend/tests/test_chat_api.py`

- [ ] **Step 1: Add failing API tests**

Append to `backend/tests/test_chat_api.py`:

```python
async def test_running_endpoint_returns_last_run_events(logged_in_client, monkeypatch):
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]

    import app.modules.sessions.streaming as streaming_mod
    streaming_mod.run_state_store.start(sid, "run-1")
    streaming_mod.run_state_store.append_event(sid, {"type": "user_text", "text": "你好"})
    streaming_mod.run_state_store.append_event(sid, {"type": "assistant_text", "text": "进行中"})

    r = await c.get(f"/api/sessions/{sid}/running")

    assert r.status_code == 200
    data = r.json()
    assert data["running"] is True
    assert data["run_id"] == "run-1"
    assert data["latest_seq"] == 2
    assert [item["event"]["type"] for item in data["events"]] == ["user_text", "assistant_text"]


async def test_running_endpoint_unknown_session_returns_404(logged_in_client):
    r = await logged_in_client.get("/api/sessions/does-not-exist/running")
    assert r.status_code == 404


async def test_running_stream_replays_after_seq(logged_in_client):
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]

    import app.modules.sessions.streaming as streaming_mod
    streaming_mod.run_state_store.start(sid, "run-1")
    streaming_mod.run_state_store.append_event(sid, {"type": "user_text", "text": "你好"})
    streaming_mod.run_state_store.append_event(sid, {"type": "assistant_text", "text": "补发"})
    streaming_mod.run_state_store.finish(sid, "completed")

    body_bytes = b""
    async with c.stream("GET", f"/api/sessions/{sid}/running/stream?after_seq=1") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        async for chunk in r.aiter_bytes():
            body_bytes += chunk

    body = body_bytes.decode("utf-8")
    data_lines = [
        json.loads(line[len("data: "):])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    assert data_lines == [{"seq": 2, "event": {"type": "assistant_text", "text": "补发"}}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend && pytest tests/test_chat_api.py::test_running_endpoint_returns_last_run_events tests/test_chat_api.py::test_running_endpoint_unknown_session_returns_404 tests/test_chat_api.py::test_running_stream_replays_after_seq -q
```

Expected: FAIL with 404 for the new endpoints.

- [ ] **Step 3: Add streaming helpers**

Modify `backend/app/modules/sessions/streaming.py` and add:

```python
async def get_running_session_state(session_id: str) -> dict:
    snapshot = run_state_store.snapshot(session_id)
    if snapshot is None:
        return {
            "running": False,
            "status": "completed",
            "events": [],
            "latest_seq": 0,
        }
    return snapshot


async def stream_running_session(session_id: str, after_seq: int) -> StreamingResponse:
    async def event_source():
        current_seq = after_seq
        while True:
            snapshot = run_state_store.snapshot(session_id, after_seq=current_seq)
            if snapshot is None:
                break
            for item in snapshot["events"]:
                current_seq = item["seq"]
                yield f"event: message\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
            if not snapshot["running"]:
                break
            await run_state_store.wait_for_change(
                session_id,
                after_seq=current_seq,
                timeout=15,
            )

    return StreamingResponse(event_source(), media_type="text/event-stream")
```

- [ ] **Step 4: Wire routes**

Modify imports in `backend/app/api/routes/sessions.py`:

```python
from app.modules.sessions.streaming import (
    get_running_session_state,
    stop_session,
    stream_running_session,
    stream_session_chat,
)
```

Add routes before `/{session_id}/chat`:

```python
@router.get("/{session_id}/running")
async def running_session(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cs = await get_owned_session_svc(db, session_id, user)
    if cs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return await get_running_session_state(session_id)


@router.get("/{session_id}/running/stream")
async def running_session_stream(
    session_id: str,
    after_seq: int = 0,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    cs = await get_owned_session_svc(db, session_id, user)
    if cs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return await stream_running_session(session_id, after_seq)
```

- [ ] **Step 5: Run targeted tests**

Run:

```bash
cd backend && pytest tests/test_chat_api.py::test_running_endpoint_returns_last_run_events tests/test_chat_api.py::test_running_endpoint_unknown_session_returns_404 tests/test_chat_api.py::test_running_stream_replays_after_seq -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/sessions/streaming.py backend/app/api/routes/sessions.py backend/tests/test_chat_api.py
git commit -m "feat: add running session recovery endpoints"
```

---

### Task 4: Frontend API Client For Recovery

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add TypeScript types**

Modify `frontend/src/types/index.ts`:

```ts
export interface RunEvent {
  seq: number;
  event: ChatEvent;
}

export interface RunningSessionState {
  running: boolean;
  run_id?: string;
  status: "running" | "completed" | "failed" | "interrupted" | string;
  events: RunEvent[];
  latest_seq: number;
  error_message?: string | null;
}
```

- [ ] **Step 2: Add API methods**

Modify imports in `frontend/src/api/client.ts` to include:

```ts
import type { ChatEvent, RunningSessionState, RunEvent } from "@/types";
```

Inside the exported `api` object, add:

```ts
  sessionRunning: (id: string) =>
    request<RunningSessionState>(`/api/sessions/${id}/running`),
```

Add a new stream function near `streamChat`:

```ts
export async function streamRunningSession(
  sessionId: string,
  afterSeq: number,
  onEvent: (item: RunEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const query = new URLSearchParams({ after_seq: String(afterSeq) });
  const res = await fetch(`/api/sessions/${sessionId}/running/stream?${query}`, {
    method: "GET",
    credentials: "same-origin",
    signal,
  });
  handleUnauthorizedResponse(res);
  if (!res.ok || !res.body) {
    onEvent({ seq: afterSeq, event: { type: "error", message: `HTTP ${res.status}` } });
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const blocks = buf.split("\n\n");
    buf = blocks.pop() ?? "";
    for (const block of blocks) {
      const line = block.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(6)) as RunEvent);
      } catch {
        // 跳过解析失败的行
      }
    }
  }
}
```

- [ ] **Step 3: Run type check**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts
git commit -m "feat: add running session client"
```

---

### Task 5: Frontend Session Restore Flow

**Files:**
- Modify: `frontend/src/pages/ChatWorkspace.tsx`

- [ ] **Step 1: Import restore stream**

Modify import:

```ts
import { api, streamChat, streamRunningSession } from "@/api/client";
```

- [ ] **Step 2: Add a shared finalizer**

Inside `ChatWorkspace`, after `loadWorkspace`, add:

```ts
  const finishStreaming = useCallback(async () => {
    setStreaming(false);
    abortRef.current = null;
    try {
      const ss = await api.sessions();
      setSessions(ss);
    } catch {
      // 忽略
    }
    loadWorkspace();
  }, [loadWorkspace]);
```

- [ ] **Step 3: Update `sendMessage` finally block**

Replace the current `finally` block in `sendMessage` with:

```ts
      } finally {
        await finishStreaming();
      }
```

Add `finishStreaming` to the `sendMessage` dependency array and remove `loadWorkspace` if it is only used by the old finally block:

```ts
    [streaming, currentId, pickedAgentId, onModeChange, attached, finishStreaming],
```

- [ ] **Step 4: Add restore helper**

Inside `ChatWorkspace`, add:

```ts
  const restoreRunningSession = useCallback(
    async (sid: string) => {
      let latestSeq = 0;
      try {
        const runningState = await api.sessionRunning(sid);
        if (!runningState.running) return;
        latestSeq = runningState.latest_seq;
        setEvents((es) => [...es, ...runningState.events.map((item) => item.event)]);
      } catch {
        return;
      }

      setStreaming(true);
      const ac = new AbortController();
      abortRef.current = ac;
      try {
        await streamRunningSession(
          sid,
          latestSeq,
          (item) => {
            if (currentIdRef.current !== sid) return;
            latestSeq = item.seq;
            setEvents((es) => [...es, item.event]);
          },
          ac.signal,
        );
      } catch {
        // 中止或网络异常都按结束流程
      } finally {
        if (currentIdRef.current === sid) {
          await finishStreaming();
        }
      }
    },
    [finishStreaming],
  );
```

- [ ] **Step 5: Call restore after history loads**

In `selectSession`, after `setEvents(msgs);`, add:

```ts
        restoreRunningSession(id);
```

Update `selectSession` dependencies:

```ts
    [currentId, onModeChange, restoreRunningSession],
```

- [ ] **Step 6: Confirm no mount-time restore effect is needed**

Do not add a separate mount-time restore effect. The current component initializes `currentId` as `null`, and会话恢复入口就是 `selectSession(id)`。Adding a second effect would risk calling `restoreRunningSession(id)` twice after a user selects a session.

Verify `const [currentId, setCurrentId] = useState<string | null>(null);` remains unchanged in `frontend/src/pages/ChatWorkspace.tsx`.

- [ ] **Step 7: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/ChatWorkspace.tsx
git commit -m "feat: restore running session stream"
```

---

### Task 6: Full Verification

**Files:**
- Verify only; no planned source edits unless a test exposes a defect.

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
cd backend && pytest tests/test_run_state.py tests/test_chat_api.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Check git status**

Run:

```bash
git status --short
```

Expected: Only unrelated pre-existing files may remain modified. Files touched by this plan should be committed.

- [ ] **Step 4: Manual verification**

Run the backend and frontend with the project’s normal commands, then verify:

```text
1. 发起一条会持续输出的智能体消息。
2. 输出过程中切到另一条会话。
3. 再切回原会话。
4. 页面显示最后一轮用户消息和已生成的 assistant 内容。
5. 后续 token 继续追加到同一轮 assistant 消息。
6. 点击停止，输入区恢复可用，工作区刷新。
```

- [ ] **Step 5: Final commit if verification required fixes**

If Step 1 or Step 2 required fixes, commit only those fixes:

```bash
git add backend/app/modules/sessions/run_state.py backend/app/modules/sessions/streaming.py backend/app/api/routes/sessions.py backend/tests/test_run_state.py backend/tests/test_chat_api.py frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/pages/ChatWorkspace.tsx
git commit -m "fix: stabilize running session recovery"
```

---

## Self-Review

- Spec coverage: The plan covers memory `RunStateStore`, chat write-through, running query, recovery SSE, frontend restore flow, stop compatibility, memory limits, and tests.
- Placeholder scan: No placeholder steps remain; code snippets include exact paths, commands, and expected outcomes.
- Type consistency: Backend uses `seq/event/latest_seq/running/status`; frontend mirrors those names with `RunEvent` and `RunningSessionState`.
