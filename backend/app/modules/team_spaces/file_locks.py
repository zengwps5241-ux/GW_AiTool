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
    """规范化团队空间内的文件相对路径，禁止越界路径。"""
    candidate = PurePosixPath(path.replace("\\", "/"))
    if candidate.is_absolute():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="非法文件路径")

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
    """返回 Agent 会话锁令牌。"""
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

    async def validate_file_lock(
        self,
        *,
        space_id: int,
        path: str,
        lock_token: str,
        now_ms: int | None = None,
    ) -> bool:
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
