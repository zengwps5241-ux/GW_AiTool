# Team Space Redis File Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Redis-backed file-level locks for team-space user editing and Agent file writes.

**Architecture:** Redis is the only lock arbiter. Backend exposes lock acquire/release APIs for frontend editing, validates `lock_token` before saving, and injects lock-aware PreToolUse hooks for Agent `Write/Edit/MultiEdit/NotebookEdit`; team-space `Bash` is denied in the first version. Locks use Lua scripts for atomic acquire, reentrant refresh, expired takeover, owner-checked release, and save validation.

**Tech Stack:** FastAPI, SQLAlchemy async, redis.asyncio, Redis Lua, pytest-asyncio, fakeredis, React, TypeScript.

---

## Engineering Review Result

The Redis lock direction is sound, but the spec had implementation holes that must be addressed by this plan:

1. Reentrancy cannot rely only on `session_id`; user editing needs a backend-issued `lock_token`, and Agent locks should use `agent:{chat_session_id}`.
2. Owner index maintenance must happen in the same Lua script as lock writes; otherwise a crash between `HSET` and `SADD` leaves locks unreleasable until TTL.
3. The first release must explicitly target single-instance Redis; Redis Cluster needs a same-slot key design before deployment.
4. Current frontend save API has no `lock_token`, so saving after lock expiry would bypass the lock unless the schema/API changes.
5. Current Agent hook builder lacks `space_id`, `user_id`, and `chat_session_id`, so runner/streaming must pass lock context into hooks.
6. Team-space `Bash` must be denied in v1; command parsing is not a reliable lock boundary.
7. Existing frontend defaults many text files to edit mode; this must change to preview-first with lock acquisition on edit.
8. Save of Office/PDF preview content may write converted Markdown, so the lock must validate the actual write path, not only the originally selected path.

## File Structure

- Modify: `backend/pyproject.toml` - add Redis runtime and fake Redis test dependencies.
- Modify: `backend/app/core/config.py` - add Redis settings.
- Create: `backend/app/core/redis.py` - shared async Redis client lifecycle.
- Create: `backend/app/modules/team_spaces/file_locks.py` - Redis key building, Lua scripts, result models, service methods.
- Modify: `backend/app/modules/workspace/text_ops.py` - expose actual content write target resolution before saving.
- Modify: `backend/app/schemas/workspace.py` - add lock request/response schemas and `lock_token` on save payload.
- Modify: `backend/app/schemas/__init__.py` - export new schemas.
- Modify: `backend/app/api/routes/team_spaces.py` - add lock endpoints and enforce lock validation on team save.
- Modify: `backend/app/integrations/claude/guard.py` - add lock-aware write hook and team-space Bash denial.
- Modify: `backend/app/integrations/claude/runner.py` - accept file-lock context and pass it to hook builder.
- Modify: `backend/app/modules/sessions/streaming.py` - build Agent lock context and release Agent locks in `finally`.
- Modify: `frontend/src/lib/workspaceApi.ts` - add optional lock APIs and `lockToken` parameter for save.
- Modify: `frontend/src/api/client.ts` - keep personal workspace save unchanged; add team lock types only where needed.
- Modify: `frontend/src/components/workspace/WorkspaceFileManager.tsx` - preview-first editing, acquire/release lock, save with token.
- Test: `backend/tests/test_team_space_file_locks.py` - Redis lock service unit tests.
- Test: `backend/tests/test_team_workspace_locks_api.py` - frontend lock/save API behavior.
- Test: `backend/tests/test_team_workspace_agent_hooks.py` - Agent hook lock and Bash behavior.
- Test: `backend/tests/test_team_workspace_streaming_locks.py` - Agent lock release on success/error/stop.
- Test: `backend/tests/test_team_workspace_file_lock_write_entries.py` - create/rename/move/delete/upload/conversion write entry lock coverage.

---

### Task 1: Redis Settings And Client

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`
- Create: `backend/app/core/redis.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Add dependencies**

Update `backend/pyproject.toml`:

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "starlette>=0.41",
    "sqlalchemy>=2.0",
    "asyncpg>=0.29",
    "passlib[bcrypt]>=1.7",
    "itsdangerous>=2.2",
    "python-multipart>=0.0.12",
    "claude-agent-sdk==0.2.89",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "httpx>=0.27",
    "openai>=1.0",
    "redis>=5.2",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "bcrypt<4.1",
    "fakeredis[lua]>=2.26",
]
```

- [ ] **Step 2: Add Redis settings test**

Append to `backend/tests/test_config.py`:

```python
def test_redis_settings_defaults(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
    settings = get_settings()

    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.team_space_file_lock_ttl_seconds == 1800
    assert settings.team_space_file_lock_cleanup_grace_seconds == 300
```

- [ ] **Step 3: Run the failing test**

Run:

```bash
cd backend && uv run pytest tests/test_config.py::test_redis_settings_defaults -q
```

Expected: FAIL because `Settings.redis_url` is not defined.

- [ ] **Step 4: Add settings**

In `backend/app/core/config.py`, add these fields to `Settings`:

```python
redis_url: str = "redis://localhost:6379/0"
team_space_file_lock_ttl_seconds: int = Field(default=1800, ge=1)
team_space_file_lock_cleanup_grace_seconds: int = Field(default=300, ge=0)
```

- [ ] **Step 5: Add shared Redis client**

Create `backend/app/core/redis.py`:

```python
"""Redis 客户端生命周期管理。"""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import get_settings

_client: Redis | None = None


def get_redis_client() -> Redis:
    """返回进程级 Redis 客户端；测试可 monkeypatch 本函数。"""
    global _client
    if _client is None:
        _client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def close_redis_client() -> None:
    """关闭 Redis 连接池，供应用生命周期或测试清理。"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
```

- [ ] **Step 6: Run settings tests**

Run:

```bash
cd backend && uv run pytest tests/test_config.py::test_redis_settings_defaults -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/app/core/config.py backend/app/core/redis.py backend/tests/test_config.py backend/uv.lock
git commit -m "feat:添加Redis锁配置"
```

---

### Task 2: Redis File Lock Service

**Files:**
- Create: `backend/app/modules/team_spaces/file_locks.py`
- Test: `backend/tests/test_team_space_file_locks.py`

- [ ] **Step 1: Write failing service tests**

Create `backend/tests/test_team_space_file_locks.py`:

```python
import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis


@pytest_asyncio.fixture
async def redis_client():
    client = FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_lock_acquire_reentrant_and_locked(redis_client):
    from app.modules.team_spaces.file_locks import FileLockService

    service = FileLockService(redis_client, ttl_seconds=30, cleanup_grace_seconds=5)

    first = await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=10,
        session_id="s1",
        lock_token="agent:s1",
    )
    assert first.ok is True
    assert first.state == "ACQUIRED"

    again = await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=10,
        session_id="s1",
        lock_token="agent:s1",
    )
    assert again.ok is True
    assert again.state == "REENTRANT"

    blocked = await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="user",
        holder_user_id=11,
        session_id="ui",
        lock_token="user-token",
    )
    assert blocked.ok is False
    assert blocked.reason == "FILE_LOCKED"
    assert blocked.locked_by is not None
    assert blocked.locked_by.session_id == "s1"


@pytest.mark.asyncio
async def test_expired_lock_can_be_taken_over(redis_client):
    from app.modules.team_spaces.file_locks import FileLockService

    service = FileLockService(redis_client, ttl_seconds=30, cleanup_grace_seconds=5)
    await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=10,
        session_id="s1",
        lock_token="agent:s1",
        now_ms=1_000,
    )

    taken = await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=11,
        session_id="s2",
        lock_token="agent:s2",
        now_ms=40_000,
    )

    assert taken.ok is True
    assert taken.state == "TAKEN_OVER_EXPIRED"


@pytest.mark.asyncio
async def test_validate_and_release_by_lock_token(redis_client):
    from app.modules.team_spaces.file_locks import FileLockService

    service = FileLockService(redis_client, ttl_seconds=30, cleanup_grace_seconds=5)
    await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="user",
        holder_user_id=10,
        session_id="ui",
        lock_token="token-a",
        now_ms=1_000,
    )

    assert await service.validate_file_lock(space_id=1, path="docs/a.md", lock_token="token-a", now_ms=2_000)
    assert not await service.validate_file_lock(space_id=1, path="docs/a.md", lock_token="token-b", now_ms=2_000)
    assert await service.release_file_lock(space_id=1, path="docs/a.md", lock_token="token-a") is True
    assert await service.validate_file_lock(space_id=1, path="docs/a.md", lock_token="token-a", now_ms=2_000) is False


@pytest.mark.asyncio
async def test_release_owner_locks_does_not_delete_taken_over_lock(redis_client):
    from app.modules.team_spaces.file_locks import FileLockService

    service = FileLockService(redis_client, ttl_seconds=30, cleanup_grace_seconds=5)
    await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=10,
        session_id="s1",
        lock_token="agent:s1",
        now_ms=1_000,
    )
    await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=11,
        session_id="s2",
        lock_token="agent:s2",
        now_ms=40_000,
    )

    released = await service.release_owner_locks("agent:s1")

    assert released == 0
    assert await service.validate_file_lock(space_id=1, path="docs/a.md", lock_token="agent:s2", now_ms=41_000)
```

- [ ] **Step 2: Run failing service tests**

Run:

```bash
cd backend && uv run pytest tests/test_team_space_file_locks.py -q
```

Expected: FAIL because `app.modules.team_spaces.file_locks` does not exist.

- [ ] **Step 3: Implement service and Lua scripts**

Create `backend/app/modules/team_spaces/file_locks.py` with:

```python
"""团队空间文件锁 Redis 实现。"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from fastapi import HTTPException, status
from redis.asyncio import Redis

HolderType = Literal["user", "agent_session"]

LOCK_ACQUIRE_SCRIPT = """
local key = KEYS[1]
local owner_index_key = KEYS[2]
local now_ms = tonumber(ARGV[1])
local expires_at_ms = tonumber(ARGV[2])
local redis_ttl_ms = tonumber(ARGV[3])
local current_session_id = redis.call("HGET", key, "session_id")
local current_lock_token = redis.call("HGET", key, "lock_token")
local current_expires_at_ms = tonumber(redis.call("HGET", key, "expires_at_ms") or "0")

local function write_lock(reason)
  redis.call("HSET", key,
    "space_id", ARGV[4],
    "path", ARGV[5],
    "holder_type", ARGV[6],
    "holder_user_id", ARGV[7],
    "session_id", ARGV[8],
    "lock_token", ARGV[9],
    "locked_at_ms", ARGV[1],
    "expires_at_ms", ARGV[2]
  )
  redis.call("PEXPIRE", key, redis_ttl_ms)
  redis.call("SADD", owner_index_key, key)
  redis.call("PEXPIRE", owner_index_key, redis_ttl_ms)
  return {"OK", reason, ARGV[2]}
end

if current_session_id == false then
  return write_lock("ACQUIRED")
end

if current_lock_token == ARGV[9] then
  redis.call("HSET", key, "expires_at_ms", ARGV[2])
  redis.call("PEXPIRE", key, redis_ttl_ms)
  redis.call("SADD", owner_index_key, key)
  redis.call("PEXPIRE", owner_index_key, redis_ttl_ms)
  return {"OK", "REENTRANT", ARGV[2]}
end

if current_expires_at_ms <= now_ms then
  return write_lock("TAKEN_OVER_EXPIRED")
end

return {
  "LOCKED",
  redis.call("HGET", key, "holder_type") or "",
  redis.call("HGET", key, "holder_user_id") or "",
  current_session_id or "",
  current_lock_token or "",
  redis.call("HGET", key, "locked_at_ms") or "",
  redis.call("HGET", key, "expires_at_ms") or ""
}
"""

LOCK_VALIDATE_SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local expected_lock_token = ARGV[2]
local current_session_id = redis.call("HGET", key, "session_id")
local current_lock_token = redis.call("HGET", key, "lock_token")
local current_expires_at_ms = tonumber(redis.call("HGET", key, "expires_at_ms") or "0")

if current_session_id == false then
  return {"EXPIRED"}
end
if current_lock_token ~= expected_lock_token then
  return {"LOCKED"}
end
if current_expires_at_ms <= now_ms then
  return {"EXPIRED"}
end
return {"OK"}
"""

LOCK_RELEASE_SCRIPT = """
local key = KEYS[1]
local owner_index_key = KEYS[2]
local expected_lock_token = ARGV[1]
local current_lock_token = redis.call("HGET", key, "lock_token")

if current_lock_token == false then
  return 0
end
if current_lock_token == expected_lock_token then
  redis.call("DEL", key)
  redis.call("SREM", owner_index_key, key)
  return 1
end
return 0
"""


@dataclass(frozen=True)
class FileLockHolder:
    holder_type: str
    holder_user_id: int | None
    session_id: str | None
    lock_token: str | None
    locked_at_ms: int | None
    expires_at_ms: int | None


@dataclass(frozen=True)
class FileLockResult:
    ok: bool
    state: str | None = None
    reason: str | None = None
    expires_at_ms: int | None = None
    locked_by: FileLockHolder | None = None


def normalize_lock_path(path: str) -> str:
    candidate = PurePosixPath(path.replace("\\\\", "/"))
    parts: list[str] = []
    for part in candidate.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="非法文件路径")
        parts.append(part)
    if not parts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件路径不能为空")
    return "/".join(parts)


def agent_lock_token(session_id: str) -> str:
    return f"agent:{session_id}"


class FileLockService:
    def __init__(self, redis: Redis, *, ttl_seconds: int, cleanup_grace_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds
        self.cleanup_grace_seconds = cleanup_grace_seconds

    def lock_key(self, space_id: int, path: str) -> str:
        normalized = normalize_lock_path(path)
        path_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"team_space:file_lock:{space_id}:{path_hash}"

    def owner_index_key(self, lock_token: str) -> str:
        return f"team_space:file_lock_owner:{lock_token}"

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    async def try_lock_file(
        self,
        *,
        space_id: int,
        path: str,
        holder_type: HolderType,
        holder_user_id: int,
        session_id: str,
        lock_token: str,
        now_ms: int | None = None,
    ) -> FileLockResult:
        normalized = normalize_lock_path(path)
        now = self._now_ms() if now_ms is None else now_ms
        expires_at_ms = now + self.ttl_seconds * 1000
        redis_ttl_ms = (self.ttl_seconds + self.cleanup_grace_seconds) * 1000
        result = await self.redis.eval(
            LOCK_ACQUIRE_SCRIPT,
            2,
            self.lock_key(space_id, normalized),
            self.owner_index_key(lock_token),
            now,
            expires_at_ms,
            redis_ttl_ms,
            space_id,
            normalized,
            holder_type,
            holder_user_id,
            session_id,
            lock_token,
        )
        if result[0] == "OK":
            return FileLockResult(ok=True, state=result[1], expires_at_ms=int(result[2]))
        return FileLockResult(
            ok=False,
            reason="FILE_LOCKED",
            locked_by=FileLockHolder(
                holder_type=result[1] or "",
                holder_user_id=int(result[2]) if result[2] else None,
                session_id=result[3] or None,
                lock_token=result[4] or None,
                locked_at_ms=int(result[5]) if result[5] else None,
                expires_at_ms=int(result[6]) if result[6] else None,
            ),
        )

    async def validate_file_lock(self, *, space_id: int, path: str, lock_token: str, now_ms: int | None = None) -> bool:
        now = self._now_ms() if now_ms is None else now_ms
        result = await self.redis.eval(LOCK_VALIDATE_SCRIPT, 1, self.lock_key(space_id, path), now, lock_token)
        return result[0] == "OK"

    async def release_file_lock(self, *, space_id: int, path: str, lock_token: str) -> bool:
        result = await self.redis.eval(
            LOCK_RELEASE_SCRIPT,
            2,
            self.lock_key(space_id, path),
            self.owner_index_key(lock_token),
            lock_token,
        )
        return int(result) == 1

    async def release_owner_locks(self, lock_token: str) -> int:
        owner_key = self.owner_index_key(lock_token)
        keys = list(await self.redis.smembers(owner_key))
        released = 0
        for key in keys:
            result = await self.redis.eval(LOCK_RELEASE_SCRIPT, 2, key, owner_key, lock_token)
            released += int(result)
        await self.redis.delete(owner_key)
        return released
```

- [ ] **Step 4: Run service tests**

Run:

```bash
cd backend && uv run pytest tests/test_team_space_file_locks.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/team_spaces/file_locks.py backend/tests/test_team_space_file_locks.py
git commit -m "feat:添加团队空间Redis文件锁服务"
```

---

### Task 3: Team Workspace Lock APIs And Save Validation

**Files:**
- Modify: `backend/app/schemas/workspace.py`
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/modules/workspace/text_ops.py`
- Modify: `backend/app/api/routes/team_spaces.py`
- Test: `backend/tests/test_team_workspace_locks_api.py`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_team_workspace_locks_api.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_team_save_requires_valid_file_lock(logged_in_client, monkeypatch):
    from fakeredis.aioredis import FakeRedis
    from app.core import redis as redis_core

    redis_client = FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_core, "get_redis_client", lambda: redis_client)

    create = await logged_in_client.post("/api/team-spaces", json={"name": "研发空间"})
    assert create.status_code == 200
    space_id = create.json()["id"]

    create_file = await logged_in_client.post(
        f"/api/team-spaces/{space_id}/workspace/file",
        json={"path": "docs/a.md", "kind": "file", "content": "old"},
    )
    assert create_file.status_code == 200

    no_lock = await logged_in_client.put(
        f"/api/team-spaces/{space_id}/workspace/content",
        json={"path": "docs/a.md", "content": "new"},
    )
    assert no_lock.status_code == 409
    assert no_lock.json()["detail"]["code"] == "FILE_LOCK_EXPIRED"

    lock = await logged_in_client.post(
        f"/api/team-spaces/{space_id}/workspace/locks",
        json={"path": "docs/a.md"},
    )
    assert lock.status_code == 200
    lock_token = lock.json()["lock_token"]

    saved = await logged_in_client.put(
        f"/api/team-spaces/{space_id}/workspace/content",
        json={"path": "docs/a.md", "content": "new", "lock_token": lock_token},
    )
    assert saved.status_code == 200
    assert saved.json()["content"] == "new"

    released = await logged_in_client.request(
        "DELETE",
        f"/api/team-spaces/{space_id}/workspace/locks",
        json={"path": "docs/a.md", "lock_token": lock_token},
    )
    assert released.status_code == 200
    assert released.json()["released"] is True

    await redis_client.aclose()
```

- [ ] **Step 2: Run failing API test**

Run:

```bash
cd backend && uv run pytest tests/test_team_workspace_locks_api.py::test_team_save_requires_valid_file_lock -q
```

Expected: FAIL because lock endpoints and `lock_token` validation do not exist.

- [ ] **Step 3: Add schemas**

In `backend/app/schemas/workspace.py`, extend `WorkspaceTextSaveIn` and add lock schemas:

```python
class WorkspaceTextSaveIn(BaseModel):
    path: str
    content: str
    lock_token: str | None = None


class WorkspaceFileLockIn(BaseModel):
    path: str


class WorkspaceFileUnlockIn(BaseModel):
    path: str
    lock_token: str


class WorkspaceFileLockOut(BaseModel):
    ok: bool
    path: str
    lock_token: str
    expires_at_ms: int


class WorkspaceFileUnlockOut(BaseModel):
    released: bool
```

Export these from `backend/app/schemas/__init__.py`.

- [ ] **Step 4: Expose actual write target**

In `backend/app/modules/workspace/text_ops.py`, add:

```python
def resolve_content_write_path(workspace: Path, rel_path: str) -> str:
    """返回保存接口实际会写入的工作区相对路径。"""
    target, resolved_path, allow_markdown = _resolve_content_target(workspace, rel_path)
    _ensure_editable_resolved_path(target, allow_markdown=allow_markdown)
    return resolved_path
```

- [ ] **Step 5: Add route helpers and endpoints**

In `backend/app/api/routes/team_spaces.py`, import `uuid4`, `get_settings`, `get_redis_client`, `FileLockService`, and new schemas. Add helper:

```python
def _file_lock_service() -> FileLockService:
    settings = get_settings()
    return FileLockService(
        get_redis_client(),
        ttl_seconds=settings.team_space_file_lock_ttl_seconds,
        cleanup_grace_seconds=settings.team_space_file_lock_cleanup_grace_seconds,
    )
```

Add endpoints before workspace content route:

```python
@router.post("/{space_id}/workspace/locks", response_model=WorkspaceFileLockOut)
async def team_lock_workspace_file(
    space_id: int,
    payload: WorkspaceFileLockIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    write_path = resolve_content_write_path(scope.root, payload.path)
    lock_token = str(uuid4())
    result = await _file_lock_service().try_lock_file(
        space_id=space_id,
        path=write_path,
        holder_type="user",
        holder_user_id=user.id,
        session_id="ui",
        lock_token=lock_token,
    )
    if not result.ok:
        raise HTTPException(status_code=409, detail={"code": "FILE_LOCKED", "path": payload.path})
    return WorkspaceFileLockOut(ok=True, path=write_path, lock_token=lock_token, expires_at_ms=result.expires_at_ms or 0)


@router.delete("/{space_id}/workspace/locks", response_model=WorkspaceFileUnlockOut)
async def team_unlock_workspace_file(
    space_id: int,
    payload: WorkspaceFileUnlockIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    write_path = resolve_content_write_path(scope.root, payload.path)
    released = await _file_lock_service().release_file_lock(
        space_id=space_id,
        path=write_path,
        lock_token=payload.lock_token,
    )
    return WorkspaceFileUnlockOut(released=released)
```

- [ ] **Step 6: Validate lock before team save**

Modify `team_save_workspace_content()`:

```python
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    write_path = resolve_content_write_path(scope.root, payload.path)
    if not payload.lock_token:
        raise HTTPException(status_code=409, detail={"code": "FILE_LOCK_EXPIRED", "path": payload.path})
    valid = await _file_lock_service().validate_file_lock(
        space_id=space_id,
        path=write_path,
        lock_token=payload.lock_token,
    )
    if not valid:
        raise HTTPException(status_code=409, detail={"code": "FILE_LOCK_EXPIRED", "path": payload.path})
    return save_content_file(scope.root, payload.path, payload.content)
```

- [ ] **Step 7: Run API tests**

Run:

```bash
cd backend && uv run pytest tests/test_team_workspace_locks_api.py tests/test_workspace_preview_unified_service.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/workspace.py backend/app/schemas/__init__.py backend/app/modules/workspace/text_ops.py backend/app/api/routes/team_spaces.py backend/tests/test_team_workspace_locks_api.py
git commit -m "feat:添加团队空间文件锁接口"
```

---

### Task 4: Agent Hook Lock Enforcement

**Files:**
- Modify: `backend/app/integrations/claude/guard.py`
- Modify: `backend/app/integrations/claude/runner.py`
- Modify: `backend/app/modules/sessions/streaming.py`
- Test: `backend/tests/test_team_workspace_agent_hooks.py`
- Test: `backend/tests/test_team_workspace_streaming_locks.py`

- [ ] **Step 1: Add failing hook tests**

Append to `backend/tests/test_team_workspace_agent_hooks.py`:

```python
@pytest.mark.asyncio
async def test_team_write_tool_acquires_file_lock(tmp_path, monkeypatch):
    from fakeredis.aioredis import FakeRedis
    from app.core import redis as redis_core
    from app.integrations.claude.guard import FileLockHookContext

    redis_client = FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_core, "get_redis_client", lambda: redis_client)

    hooks = build_pre_tool_use_hooks(
        tmp_path,
        can_write=True,
        file_lock_context=FileLockHookContext(space_id=1, user_id=10, session_id="s1"),
    )
    write_hook = next(h for h in hooks if h.matcher == "Write|Edit|MultiEdit|NotebookEdit").hooks[0]

    result = await write_hook(
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "docs" / "a.md")}},
        "toolu_1",
        {},
    )

    assert result["hookSpecificOutput"]["permissionDecision"] == "allow"
    await redis_client.aclose()


@pytest.mark.asyncio
async def test_team_bash_is_denied_even_when_workspace_writable(tmp_path):
    from app.integrations.claude.guard import FileLockHookContext

    hooks = build_pre_tool_use_hooks(
        tmp_path,
        can_write=True,
        file_lock_context=FileLockHookContext(space_id=1, user_id=10, session_id="s1"),
    )
    bash_hook = next(h for h in hooks if h.matcher == "Bash").hooks[0]

    result = await bash_hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}, "toolu_1", {})

    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "团队空间中请使用 Read/Write/Edit/MultiEdit 工具" in result["hookSpecificOutput"]["permissionDecisionReason"]
```

- [ ] **Step 2: Run failing hook tests**

Run:

```bash
cd backend && uv run pytest tests/test_team_workspace_agent_hooks.py -q
```

Expected: FAIL because `FileLockHookContext` and lock hook do not exist.

- [ ] **Step 3: Add hook context and write hook**

In `backend/app/integrations/claude/guard.py`, add:

```python
from dataclasses import dataclass
from app.core.config import get_settings
from app.core.redis import get_redis_client
from app.modules.team_spaces.file_locks import FileLockService, agent_lock_token, normalize_lock_path


@dataclass(frozen=True)
class FileLockHookContext:
    space_id: int
    user_id: int
    session_id: str


def _allow() -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}
```

Add `_team_file_lock_hook()`:

```python
def _team_file_lock_hook(user_workspace: Path, context: FileLockHookContext):
    async def guard(input_data, _tool_use_id, _context):
        tool_name = input_data.get("tool_name")
        tool_input = input_data.get("tool_input") or {}
        raw_path = tool_input.get("notebook_path") if tool_name == "NotebookEdit" else tool_input.get("file_path")
        if not raw_path:
            return _deny("缺少文件路径，已阻止团队空间写入")
        try:
            abs_path = Path(raw_path)
            if not abs_path.is_absolute():
                abs_path = user_workspace / abs_path
            resolved = abs_path.resolve()
            rel = resolved.relative_to(user_workspace.resolve()).as_posix()
            normalized = normalize_lock_path(rel)
        except Exception:
            return _deny("文件路径不在当前团队空间内，已阻止写入")

        settings = get_settings()
        service = FileLockService(
            get_redis_client(),
            ttl_seconds=settings.team_space_file_lock_ttl_seconds,
            cleanup_grace_seconds=settings.team_space_file_lock_cleanup_grace_seconds,
        )
        result = await service.try_lock_file(
            space_id=context.space_id,
            path=normalized,
            holder_type="agent_session",
            holder_user_id=context.user_id,
            session_id=context.session_id,
            lock_token=agent_lock_token(context.session_id),
        )
        if result.ok:
            return _allow()
        return _deny(f"文件正在被其他用户或会话编辑，已阻止本次写入。path={normalized}")

    return guard
```

Modify `build_pre_tool_use_hooks()` signature:

```python
def build_pre_tool_use_hooks(
    user_workspace: Path,
    *,
    can_write: bool = True,
    readonly_reason: str | None = None,
    agent_workdir: Path | None = None,
    file_lock_context: FileLockHookContext | None = None,
) -> list[HookMatcher]:
```

Behavior:

```python
if file_lock_context is not None:
    hooks = [
        HookMatcher(matcher="Write|Edit|MultiEdit|NotebookEdit", hooks=[_team_file_lock_hook(user_workspace, file_lock_context)]),
        HookMatcher(matcher="Bash", hooks=[_readonly_tool_hook("团队空间中请使用 Read/Write/Edit/MultiEdit 工具，Bash 已禁用")]),
    ]
elif not can_write:
    ...
else:
    hooks = [HookMatcher(matcher="Bash", hooks=[_bash_safety_hook(...)])]
```

- [ ] **Step 4: Pass context through runner**

In `backend/app/integrations/claude/runner.py`, add parameter:

```python
file_lock_context: FileLockHookContext | None = None,
```

Pass it into `build_pre_tool_use_hooks(..., file_lock_context=file_lock_context)`.

- [ ] **Step 5: Build and release Agent lock context**

In `backend/app/modules/sessions/streaming.py`, when `scope.kind == "team"` pass:

```python
from app.integrations.claude.guard import FileLockHookContext
from app.modules.team_spaces.file_locks import FileLockService, agent_lock_token
from app.core.config import get_settings
from app.core.redis import get_redis_client
```

Inside `runner()` before `stream_chat`:

```python
if scope.kind == "team":
    stream_kwargs["file_lock_context"] = FileLockHookContext(
        space_id=int(scope.key),
        user_id=user.id,
        session_id=str(session_id),
    )
```

In `finally`, release Agent locks:

```python
if scope.kind == "team":
    settings = get_settings()
    service = FileLockService(
        get_redis_client(),
        ttl_seconds=settings.team_space_file_lock_ttl_seconds,
        cleanup_grace_seconds=settings.team_space_file_lock_cleanup_grace_seconds,
    )
    await service.release_owner_locks(agent_lock_token(str(session_id)))
```

- [ ] **Step 6: Run hook tests**

Run:

```bash
cd backend && uv run pytest tests/test_team_workspace_agent_hooks.py tests/test_claude_guard.py -q
```

Expected: PASS.

- [ ] **Step 7: Add streaming release test**

Create `backend/tests/test_team_workspace_streaming_locks.py`:

```python
import pytest
from fakeredis.aioredis import FakeRedis


@pytest.mark.asyncio
async def test_streaming_releases_agent_file_locks(app_env, monkeypatch):
    from app.core import redis as redis_core
    from app.integrations.claude.runner import ChatRunSummary
    from app.models import Agent, ChatSession, TeamSpace, TeamSpaceMember, User
    from app.modules.sessions import streaming
    from app.modules.team_spaces.file_locks import FileLockService, agent_lock_token
    from app.db.session import async_session

    redis_client = FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_core, "get_redis_client", lambda: redis_client)

    async with async_session() as db:
        user = User(username="alice", password_hash="x")
        db.add(user)
        await db.flush()
        space = TeamSpace(name="研发空间", owner_user_id=user.id)
        db.add(space)
        await db.flush()
        db.add(TeamSpaceMember(space_id=space.id, user_id=user.id, role="editor"))
        agent = Agent(name="Writer", code="writer", system_prompt="")
        db.add(agent)
        await db.flush()
        cs = ChatSession(id="session-1", user_id=user.id, agent_id=agent.id, workspace_kind="team", team_space_id=space.id)
        db.add(cs)
        await db.commit()
        await db.refresh(cs)
        await db.refresh(agent)

    async def fake_stream_chat(**kwargs):
        context = kwargs["file_lock_context"]
        service = FileLockService(redis_client, ttl_seconds=1800, cleanup_grace_seconds=300)
        await service.try_lock_file(
            space_id=context.space_id,
            path="docs/a.md",
            holder_type="agent_session",
            holder_user_id=context.user_id,
            session_id=context.session_id,
            lock_token=agent_lock_token(context.session_id),
        )
        return ChatRunSummary(
            session_id="claude-session-1",
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

    monkeypatch.setattr(streaming, "stream_chat", fake_stream_chat)

    response = await streaming.stream_session_chat(cs, user, "写 docs/a.md", agent=agent)
    # 消费 SSE，等待后台 runner 结束并触发 finally 释放锁。
    async for _chunk in response.body_iterator:
        pass

    service = FileLockService(redis_client, ttl_seconds=1800, cleanup_grace_seconds=300)
    assert await service.validate_file_lock(
        space_id=space.id,
        path="docs/a.md",
        lock_token=agent_lock_token("session-1"),
    ) is False
    await redis_client.aclose()
```

Run:

```bash
cd backend && uv run pytest tests/test_team_workspace_streaming_locks.py -q
```

Expected: PASS after implementation.

- [ ] **Step 8: Commit**

```bash
git add backend/app/integrations/claude/guard.py backend/app/integrations/claude/runner.py backend/app/modules/sessions/streaming.py backend/tests/test_team_workspace_agent_hooks.py backend/tests/test_team_workspace_streaming_locks.py
git commit -m "feat:接入Agent文件锁hook"
```

---

### Task 5: Frontend Preview-First Edit Locking

**Files:**
- Modify: `frontend/src/lib/workspaceApi.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/workspace/WorkspaceFileManager.tsx`

- [ ] **Step 1: Extend workspace API types**

In `frontend/src/lib/workspaceApi.ts`, update `WorkspaceApi`:

```ts
  lockFile?(path: string): Promise<{ ok: boolean; path: string; lock_token: string; expires_at_ms: number }>;
  unlockFile?(path: string, lockToken: string): Promise<{ released: boolean }>;
  saveContent(path: string, content: string, lockToken?: string): Promise<{
```

For personal workspace:

```ts
saveContent: (path, content) => api.workspaceSaveContent(path, content),
```

For team workspace:

```ts
lockFile: (path: string) =>
  request(`${workspaceBase}/locks`, {
    method: "POST",
    body: JSON.stringify({ path }),
  }),
unlockFile: (path: string, lockToken: string) =>
  request(`${workspaceBase}/locks`, {
    method: "DELETE",
    body: JSON.stringify({ path, lock_token: lockToken }),
  }),
saveContent: (path: string, content: string, lockToken?: string) =>
  request(`${workspaceBase}/content`, {
    method: "PUT",
    body: JSON.stringify({ path, content, lock_token: lockToken }),
  }),
```

- [ ] **Step 2: Make frontend default to preview**

In `WorkspaceFileManager.tsx`, change:

```ts
const [previewMode, setPreviewMode] = useState<"preview" | "edit">("preview");
```

Change `selectNode()` to always set `"preview"` for files.

- [ ] **Step 3: Track current lock**

Add state:

```ts
const [fileLock, setFileLock] = useState<{ path: string; token: string } | null>(null);
const fileLockRef = useRef(fileLock);
fileLockRef.current = fileLock;
```

Add helper:

```ts
const releaseCurrentLock = useCallback(async () => {
  const current = fileLockRef.current;
  if (!current || !api.unlockFile) return;
  setFileLock(null);
  try {
    await api.unlockFile(current.path, current.token);
  } catch {
    // 释放失败由 Redis TTL 兜底；前端不阻塞用户导航。
  }
}, [api]);
```

- [ ] **Step 4: Acquire lock before entering edit mode**

Modify `switchMode()` so `mode === "edit"` first calls `api.lockFile(selected.path)` for team workspace. On failure, show error toast and keep preview mode.

```ts
const enterEditMode = useCallback(async () => {
  if (!selected || selected.type !== "file") return;
  if (!ensureWritable()) return;
  if (api.lockFile) {
    try {
      const locked = await api.lockFile(selected.path);
      setFileLock({ path: selected.path, token: locked.lock_token });
    } catch (e) {
      showToast(`文件加锁失败：${formatErrorMessage(e)}`, "error");
      return;
    }
  }
  setPreviewMode("edit");
  setPreviewReloadKey((v) => v + 1);
}, [api, ensureWritable, selected, showToast]);
```

When switching back to preview, call `releaseCurrentLock()` after unsaved confirmation.

- [ ] **Step 5: Save with lock token**

Modify `save()`:

```ts
if (api.kind === "team" && !fileLock?.token) {
  showToast("编辑锁已失效，请重新进入编辑模式", "error");
  setPreviewMode("preview");
  return;
}
const saved = await api.saveContent(selected.path, content, fileLock?.token);
```

On a `FILE_LOCK_EXPIRED` or `FILE_LOCKED` error, clear `fileLock`, switch to preview, and show the backend message.

- [ ] **Step 6: Release on file switch, clear selection, and unmount**

Before selecting another file or clearing selection, call `releaseCurrentLock()` after unsaved confirmation. Add:

```ts
useEffect(() => {
  return () => {
    const current = fileLockRef.current;
    if (current && api.unlockFile) {
      void api.unlockFile(current.path, current.token);
    }
  };
}, [api]);
```

- [ ] **Step 7: Build frontend**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/workspaceApi.ts frontend/src/api/client.ts frontend/src/components/workspace/WorkspaceFileManager.tsx
git commit -m "feat:接入前端文件编辑锁"
```

---

### Task 6: Cover Other Team Write Entries

**Files:**
- Modify: `backend/app/api/routes/team_spaces.py`
- Modify: `backend/app/modules/conversions/service.py`
- Test: `backend/tests/test_team_workspace_file_lock_write_entries.py`
- Existing tests: `backend/tests/test_team_workspace_api.py`, `backend/tests/test_uploads_api.py`, `backend/tests/test_conversion_tasks_api.py`

- [ ] **Step 1: Write failing route tests for file operation conflicts**

Create `backend/tests/test_team_workspace_file_lock_write_entries.py`:

```python
import pytest
from fakeredis.aioredis import FakeRedis


@pytest.fixture
async def redis_client(monkeypatch):
    from app.core import redis as redis_core

    client = FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_core, "get_redis_client", lambda: client)
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_team_file_delete_is_blocked_by_existing_lock(logged_in_client, redis_client):
    from app.modules.team_spaces.file_locks import FileLockService

    create = await logged_in_client.post("/api/team-spaces", json={"name": "研发空间"})
    assert create.status_code == 200
    space_id = create.json()["id"]
    created = await logged_in_client.post(
        f"/api/team-spaces/{space_id}/workspace/file",
        json={"path": "docs/a.md", "kind": "file", "content": "old"},
    )
    assert created.status_code == 200

    service = FileLockService(redis_client, ttl_seconds=1800, cleanup_grace_seconds=300)
    await service.try_lock_file(
        space_id=space_id,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=999,
        session_id="agent-session",
        lock_token="agent:agent-session",
    )

    deleted = await logged_in_client.delete(f"/api/team-spaces/{space_id}/workspace/file?path=docs%2Fa.md")

    assert deleted.status_code == 409
    assert deleted.json()["detail"]["code"] == "FILE_LOCKED"
```

- [ ] **Step 2: Run failing write-entry test**

Run:

```bash
cd backend && uv run pytest tests/test_team_workspace_file_lock_write_entries.py::test_team_file_delete_is_blocked_by_existing_lock -q
```

Expected: FAIL because delete does not check file locks.

- [ ] **Step 3: Add temporary lock helpers for one-shot user operations**

In `backend/app/api/routes/team_spaces.py`, add:

```python
async def _acquire_temporary_user_file_lock(
    *,
    space_id: int,
    path: str,
    user: User,
    operation: str,
) -> str:
    lock_token = f"user-op:{operation}:{uuid4()}"
    result = await _file_lock_service().try_lock_file(
        space_id=space_id,
        path=path,
        holder_type="user",
        holder_user_id=user.id,
        session_id="api",
        lock_token=lock_token,
    )
    if not result.ok:
        raise HTTPException(status_code=409, detail={"code": "FILE_LOCKED", "path": path})
    return lock_token


async def _release_temporary_user_file_lock(*, space_id: int, path: str, lock_token: str) -> None:
    await _file_lock_service().release_file_lock(space_id=space_id, path=path, lock_token=lock_token)
```

- [ ] **Step 4: Wrap file create, rename, move, delete, and upload writes**

Use the helper in these functions:

```python
@router.post("/{space_id}/workspace/file")
async def team_create_workspace_item(...):
    ...
    if payload.kind == "file":
        lock_token = await _acquire_temporary_user_file_lock(space_id=space_id, path=payload.path, user=user, operation="create")
        try:
            return create_workspace_item(scope.root, payload.path, payload.kind, payload.content)
        finally:
            await _release_temporary_user_file_lock(space_id=space_id, path=payload.path, lock_token=lock_token)
    return create_workspace_item(scope.root, payload.path, payload.kind, payload.content)
```

Apply the same pattern:

- `team_rename_workspace_item`: lock `payload.path`.
- `team_move_workspace_item`: lock `payload.path`.
- `team_delete_workspace_item`: lock `path`.
- `upload_team_task_file`: resolve the upload task final path before saving, lock that path, release in `finally`.

For upload path resolution, add a small helper in `backend/app/modules/uploads/tasks.py` if no existing function exposes the final path:

```python
async def get_upload_task_target_path(db: AsyncSession, task_id: int) -> str:
    task = await db.get(UploadTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="上传任务不存在")
    return str(PurePosixPath(task.target_dir or "") / task.filename)
```

- [ ] **Step 5: Lock conversion writes inside the worker**

In `backend/app/modules/conversions/service.py`, import `get_redis_client`, `FileLockService`, and settings. Inside `run_conversion_task()` after `task` is loaded and `workspace_kind/team_space_id` are known:

```python
lock_token: str | None = None
if workspace_kind == "team" and team_space_id is not None:
    lock_token = f"conversion:{task.id}"
    service = FileLockService(
        get_redis_client(),
        ttl_seconds=settings.team_space_file_lock_ttl_seconds,
        cleanup_grace_seconds=settings.team_space_file_lock_cleanup_grace_seconds,
    )
    result = await service.try_lock_file(
        space_id=team_space_id,
        path=task.source_path,
        holder_type="agent_session",
        holder_user_id=0,
        session_id=f"conversion:{task.id}",
        lock_token=lock_token,
    )
    if not result.ok:
        task.status = "failed"
        task.error_message = "文件正在被其他用户或会话编辑"
        task.finished_at = datetime.now(UTC)
        await session.commit()
        return
```

In the existing `finally`, release if acquired:

```python
if lock_token and team_space_id is not None:
    await service.release_file_lock(space_id=team_space_id, path=task.source_path, lock_token=lock_token)
```

- [ ] **Step 6: Run write-entry tests**

Run:

```bash
cd backend && uv run pytest \
  tests/test_team_workspace_file_lock_write_entries.py \
  tests/test_team_workspace_api.py \
  tests/test_uploads_api.py \
  tests/test_conversion_tasks_api.py \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/team_spaces.py backend/app/modules/uploads/tasks.py backend/app/modules/conversions/service.py backend/tests/test_team_workspace_file_lock_write_entries.py
git commit -m "feat:覆盖团队空间其他写入口文件锁"
```

---

### Task 7: Full Verification

**Files:**
- No new files unless fixing failures.

- [ ] **Step 1: Run backend focused tests**

```bash
cd backend && uv run pytest \
  tests/test_team_space_file_locks.py \
  tests/test_team_workspace_locks_api.py \
  tests/test_team_workspace_agent_hooks.py \
  tests/test_team_workspace_streaming_locks.py \
  tests/test_team_spaces_api.py \
  tests/test_workspace_preview_unified_service.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Run formatting/diff checks**

```bash
git diff --check
git status --short
```

Expected: `git diff --check` exits 0. `git status --short` contains only intentional files before final commit.

- [ ] **Step 4: Final commit if verification changed files**

```bash
git add backend frontend
git commit -m "test:验证团队空间文件锁"
```

Skip this commit if all previous task commits already include all changes and there are no remaining modifications.

---

## Self-Review

Spec coverage:

- Redis atomic acquire/reentrant/expired takeover: Task 2.
- Owner-checked release and owner index cleanup: Task 2 and Task 4.
- User edit lock acquisition, release, save validation: Task 3 and Task 5.
- Agent write hook and Bash denial: Task 4.
- Session end/error/stop release: Task 4.
- Actual write path for converted Markdown saves: Task 3.
- Upload/conversion/create/rename/move/delete write entry locking: Task 6.
- Tests for lock conflicts, expiry, reentrancy, frontend save contract, hook behavior, and write entry coverage: Tasks 2-7.

Known scope decisions:

- The first implementation targets single-instance Redis, not Redis Cluster.
- Directory creation remains permission-guarded but not file-locked.

Plan complete and saved to `docs/superpowers/plans/2026-06-06-team-space-file-lock-redis.md`.
